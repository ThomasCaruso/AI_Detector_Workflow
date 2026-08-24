"""Tests for personal-experiment approval, hashing, and dataset compilation.

All fixtures are synthetic. The suite never reads the gitignored personal
corpus or any of the user's prose.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from authorship_shift.lora_data import parse_example, validate_dataset
from authorship_shift.personal_dataset import (
    APPROVED,
    FALLBACK_INSTRUCTION,
    INSTRUCTION_BY_FUNCTION,
    NEEDS_REVIEW,
    annotation_set_sha256,
    approve_packet,
    approve_packets,
    build_manifest,
    compile_row,
    compile_rows,
    dataset_sha256,
    instruction_for,
    serialize_rows,
    split_rows,
    target_words,
)

CORPUS = "c" * 64
MASK = "m" * 64


def _packet(example_id="essay#u00", split="train", source_id="essay", **overrides):
    packet = {
        "example_id": example_id,
        "source_id": source_id,
        "split": split,
        "source_region_ids": [f"{source_id}:b0000"],
        "corpus_sha256": CORPUS,
        "eligibility_mask_sha256": MASK,
        "target_text": " ".join(f"word{i}" for i in range(60)),
        "semantic_plan": {
            "content_atoms": ["A first claim is made.", "A second claim follows."],
            "immutable_details": ["the figure is Whitlock"],
            "required_qualifications": ["the claim is hedged rather than absolute"],
            "communicative_function": "reflect",
        },
        "review_status": NEEDS_REVIEW,
    }
    packet.update(overrides)
    return packet


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


def test_approval_changes_only_the_status() -> None:
    packet = _packet()

    approved = approve_packet(packet)

    assert approved["review_status"] == APPROVED
    before = {k: v for k, v in packet.items() if k != "review_status"}
    after = {k: v for k, v in approved.items() if k != "review_status"}
    assert before == after


def test_approval_does_not_mutate_the_input() -> None:
    packet = _packet()

    approve_packet(packet)

    assert packet["review_status"] == NEEDS_REVIEW


def test_approving_an_already_approved_packet_is_idempotent() -> None:
    approved = approve_packet(_packet(review_status=APPROVED))

    assert approved["review_status"] == APPROVED


def test_approving_from_an_unknown_status_is_refused() -> None:
    with pytest.raises(ValueError):
        approve_packet(_packet(review_status="rejected"))


# ---------------------------------------------------------------------------
# Annotation-set hash
# ---------------------------------------------------------------------------


def test_annotation_hash_is_deterministic() -> None:
    packets = approve_packets([_packet(), _packet(example_id="essay#u01")])

    assert annotation_set_sha256(packets) == annotation_set_sha256(packets)


def test_annotation_hash_ignores_packet_order() -> None:
    a, b = approve_packets([_packet(), _packet(example_id="essay#u01")])

    assert annotation_set_sha256([a, b]) == annotation_set_sha256([b, a])


def test_annotation_hash_ignores_plan_key_order() -> None:
    packet = approve_packet(_packet())
    reordered = dict(packet)
    plan = packet["semantic_plan"]
    reordered["semantic_plan"] = {k: plan[k] for k in reversed(list(plan))}

    assert annotation_set_sha256([packet]) == annotation_set_sha256([reordered])


def test_mutating_a_content_atom_changes_the_annotation_hash() -> None:
    packet = approve_packet(_packet())
    original = annotation_set_sha256([packet])

    plan = dict(packet["semantic_plan"])
    plan["content_atoms"] = [*plan["content_atoms"][:-1], "A different second claim."]
    mutated = {**packet, "semantic_plan": plan}

    assert annotation_set_sha256([mutated]) != original
    # And restoring returns the original digest.
    assert annotation_set_sha256([approve_packet(_packet())]) == original


@pytest.mark.parametrize(
    "field,value",
    [
        ("target_text", "entirely different prose here"),
        ("split", "holdout"),
        ("source_id", "other-doc"),
        ("source_region_ids", ["essay:b0009"]),
        ("review_status", NEEDS_REVIEW),
        ("corpus_sha256", "d" * 64),
        ("eligibility_mask_sha256", "e" * 64),
    ],
)
def test_every_bound_field_moves_the_annotation_hash(field: str, value) -> None:
    packet = approve_packet(_packet())
    original = annotation_set_sha256([packet])

    assert annotation_set_sha256([{**packet, field: value}]) != original


def test_a_packet_missing_a_bound_field_is_refused() -> None:
    packet = approve_packet(_packet())
    del packet["corpus_sha256"]

    with pytest.raises(ValueError, match="missing hash-bound fields"):
        annotation_set_sha256([packet])


# ---------------------------------------------------------------------------
# Instruction mapping
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("function", sorted(INSTRUCTION_BY_FUNCTION))
def test_each_communicative_function_maps_to_its_instruction(function: str) -> None:
    assert instruction_for(function) == INSTRUCTION_BY_FUNCTION[function]


@pytest.mark.parametrize("value", [None, "", "  ", "unknown-function"])
def test_a_missing_or_unknown_function_falls_back(value) -> None:
    assert instruction_for(value) == FALLBACK_INSTRUCTION


def test_no_instruction_carries_style_or_detector_language() -> None:
    banned = ("like thomas", "voice", "tone", "sentence", "vocabulary", "detector", "human")
    for instruction in (*INSTRUCTION_BY_FUNCTION.values(), FALLBACK_INSTRUCTION):
        lowered = instruction.lower()
        assert not any(word in lowered for word in banned), instruction


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


def test_only_approved_packets_compile() -> None:
    with pytest.raises(ValueError, match="only approved"):
        compile_row(_packet(), annotation_digest="a" * 64)


def test_a_compiled_row_parses_as_a_lora_example() -> None:
    row = compile_row(approve_packet(_packet()), annotation_digest="a" * 64)

    example = parse_example(row)

    assert example.genre == "personal_academic"
    assert example.split == "train"
    assert example.provenance.kind == "user_owned"
    assert example.metadata["experiment_id"] == "personal-style-b-v1"
    assert example.metadata["annotation_set_sha256"] == "a" * 64


def test_compiled_rows_are_ordered_by_id() -> None:
    packets = approve_packets(
        [_packet(example_id="essay#u02"), _packet(example_id="essay#u00")]
    )

    rows = compile_rows(packets, annotation_digest="a" * 64)

    assert [row["id"] for row in rows] == ["essay#u00", "essay#u02"]


def test_compilation_carries_target_text_through_unchanged() -> None:
    packet = approve_packet(_packet(target_text="  Spacing and “quotes” kept.  "))

    row = compile_row(packet, annotation_digest="a" * 64)

    assert row["target_text"] == "  Spacing and “quotes” kept.  "


# ---------------------------------------------------------------------------
# Dataset hashing and splitting
# ---------------------------------------------------------------------------


def test_dataset_hash_is_deterministic_and_matches_serialized_bytes() -> None:
    rows = compile_rows(approve_packets([_packet()]), annotation_digest="a" * 64)

    assert dataset_sha256(rows) == dataset_sha256(rows)
    assert dataset_sha256(rows) == hashlib.sha256(serialize_rows(rows)).hexdigest()


def test_serialized_rows_use_newline_endings_only() -> None:
    rows = compile_rows(approve_packets([_packet()]), annotation_digest="a" * 64)

    payload = serialize_rows(rows)

    assert b"\r\n" not in payload
    assert payload.endswith(b"\n")


def test_dataset_hash_changes_with_content() -> None:
    rows = compile_rows(approve_packets([_packet()]), annotation_digest="a" * 64)
    other = compile_rows(approve_packets([_packet()]), annotation_digest="b" * 64)

    assert dataset_sha256(rows) != dataset_sha256(other)


def test_split_rows_separate_train_from_holdout() -> None:
    packets = approve_packets(
        [
            _packet(example_id="essay#u00", split="train", source_id="essay"),
            _packet(example_id="diary#u00", split="holdout", source_id="diary"),
        ]
    )
    rows = compile_rows(packets, annotation_digest="a" * 64)

    train = split_rows(rows, "train")
    holdout = split_rows(rows, "holdout")

    assert [row["id"] for row in train] == ["essay#u00"]
    assert [row["id"] for row in holdout] == ["diary#u00"]
    assert all(row["split"] == "train" for row in train)
    assert all(row["split"] == "holdout" for row in holdout)


def test_manifest_binds_every_digest_and_count() -> None:
    packets = approve_packets(
        [
            _packet(example_id="essay#u00", split="train", source_id="essay"),
            _packet(example_id="diary#u00", split="holdout", source_id="diary"),
        ]
    )
    digest = annotation_set_sha256(packets)
    rows = compile_rows(packets, annotation_digest=digest)

    manifest = build_manifest(
        rows,
        corpus_sha256=CORPUS,
        eligibility_mask_sha256=MASK,
        annotation_set_digest=digest,
    ).to_dict()

    assert manifest["corpus_sha256"] == CORPUS
    assert manifest["eligibility_mask_sha256"] == MASK
    assert manifest["annotation_set_sha256"] == digest
    assert manifest["train_example_count"] == 1
    assert manifest["holdout_example_count"] == 1
    assert manifest["train_dataset_sha256"] == dataset_sha256(split_rows(rows, "train"))
    assert manifest["holdout_dataset_sha256"] == dataset_sha256(split_rows(rows, "holdout"))
    assert manifest["full_dataset_sha256"] == dataset_sha256(rows)
    assert manifest["source_ids_by_split"] == {"holdout": ["diary"], "train": ["essay"]}
    assert manifest["compiler"].startswith("personal-dataset-compiler/")


def test_target_words_counts_only_the_given_rows() -> None:
    rows = compile_rows(approve_packets([_packet()]), annotation_digest="a" * 64)

    assert target_words(rows) == 60


def test_a_compiled_personal_dataset_validates() -> None:
    packets = approve_packets(
        [
            _packet(example_id="essay#u00", split="train", source_id="essay"),
            _packet(
                example_id="diary#u00",
                split="holdout",
                source_id="diary",
                target_text=" ".join(f"other{i}" for i in range(60)),
            ),
        ]
    )
    rows = compile_rows(packets, annotation_digest="a" * 64)

    report = validate_dataset([parse_example(row) for row in rows])

    assert report.valid, report.errors
    # A personal pilot has no dev split by design; that warning is expected.
    assert any("no dev examples" in warning for warning in report.warnings)


def test_no_compiled_row_carries_a_detector_field() -> None:
    rows = compile_rows(approve_packets([_packet()]), annotation_digest="a" * 64)

    blob = json.dumps(rows).lower()

    for banned in ("detector_score", "detector_target", "detector_label", "pangram", "quillbot"):
        assert banned not in blob
