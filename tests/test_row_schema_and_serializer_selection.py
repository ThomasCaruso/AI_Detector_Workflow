"""Tests for the versioned row schema and config-driven serializer selection.

Every packet here is synthetic. No corpus document, no user prose.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from authorship_shift.lora_data import parse_example
from authorship_shift.personal_dataset import (
    APPROVED,
    ROW_SCHEMA_V1,
    ROW_SCHEMA_V2,
    ROW_SCHEMAS,
    compile_row,
    compile_rows,
)
from authorship_shift.plan_serialization import SERIALIZER_V1, SERIALIZER_V2

DIGEST = "d" * 64


def _packet(function="explain", *, include_function=True, example_id="alpha#u00"):
    plan = {
        "content_atoms": ["Alpha is stated.", "Beta follows."],
        "immutable_details": ["the figure is 42"],
        "required_qualifications": ["the claim is hedged"],
    }
    if include_function:
        plan["communicative_function"] = function
    return {
        "example_id": example_id,
        "source_id": "alpha",
        "split": "train",
        "source_region_ids": ["alpha:b0000"],
        "corpus_sha256": "a" * 64,
        "eligibility_mask_sha256": "b" * 64,
        "target_words": 12,
        "region_flags": [],
        "oversized_single_paragraph": False,
        "target_text": "Synthetic target prose written for this test only.",
        "semantic_plan": plan,
        "fidelity": {"passed": True, "failures": [], "warnings": []},
        "review_status": APPROVED,
    }


def _trainer():
    path = Path(__file__).resolve().parents[1] / "research" / "lora" / "train_personal_qlora.py"
    spec = importlib.util.spec_from_file_location("_trainer_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# --- row schema v1 byte-stability -----------------------------------------

def test_v1_is_the_default_row_schema():
    assert compile_row(_packet(), annotation_digest=DIGEST) == compile_row(
        _packet(), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V1
    )


def test_v1_carries_no_communicative_function_anywhere():
    row = compile_row(_packet(), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V1)

    assert "communicative_function" not in row
    assert "communicative_function" not in row["metadata"]
    assert "row_schema" not in row["metadata"]


def test_v1_bytes_are_unchanged_by_the_v2_addition():
    """v1 rows are bound into frozen B and C dataset digests."""

    row = compile_row(_packet(), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V1)

    assert sorted(row) == [
        "content_atoms", "genre", "id", "immutable_details", "instruction",
        "metadata", "provenance", "required_qualifications", "split", "target_text",
    ]
    assert sorted(row["metadata"]) == [
        "annotation_set_sha256", "corpus_sha256", "eligibility_mask_sha256",
        "experiment_id", "source_region_ids",
    ]


# --- row schema v2 ---------------------------------------------------------

def test_v2_carries_communicative_function_from_the_packet():
    row = compile_row(_packet("persuade"), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V2)

    assert row["metadata"]["communicative_function"] == "persuade"
    assert row["metadata"]["row_schema"] == ROW_SCHEMA_V2


def test_v2_absent_function_stays_absent():
    row = compile_row(
        _packet(include_function=False), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V2
    )

    assert "communicative_function" not in row["metadata"]


def test_v2_null_function_stays_null():
    row = compile_row(_packet(None), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V2)

    assert row["metadata"]["communicative_function"] is None


def test_v2_does_not_infer_function_from_instruction():
    """A missing function must not be reconstructed from the derived instruction."""

    packet = _packet(include_function=False)
    row = compile_row(packet, annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V2)

    assert row["instruction"]  # an instruction is still produced
    assert "communicative_function" not in row["metadata"]


def test_v2_preserves_all_other_fields_identically_to_v1():
    one = compile_row(_packet(), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V1)
    two = compile_row(_packet(), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V2)

    for key in one:
        if key != "metadata":
            assert one[key] == two[key]
    for key in one["metadata"]:
        assert one["metadata"][key] == two["metadata"][key]


def test_v2_survives_parse_example_into_metadata():
    """Top-level keys are dropped by the parser; metadata is not."""

    row = compile_row(_packet("analyze"), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V2)
    example = parse_example(json.loads(json.dumps(row)))

    assert example.metadata["communicative_function"] == "analyze"


def test_unknown_row_schema_fails_closed():
    with pytest.raises(ValueError, match="unknown row schema"):
        compile_row(_packet(), annotation_digest=DIGEST, row_schema="personal-dataset-row/v9")


def test_compile_rows_threads_the_schema():
    rows = compile_rows(
        [_packet(example_id="alpha#u00"), _packet(example_id="alpha#u01")],
        annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V2,
    )

    assert len(rows) == 2
    assert all(r["metadata"]["row_schema"] == ROW_SCHEMA_V2 for r in rows)


def test_row_schemas_are_pinned():
    assert ROW_SCHEMAS == (ROW_SCHEMA_V1, ROW_SCHEMA_V2)


# --- serializer selection --------------------------------------------------

def test_absent_serializer_version_resolves_to_v1():
    assert _trainer().serializer_version_for({}) == SERIALIZER_V1


def test_explicit_v1_resolves_to_v1():
    assert _trainer().serializer_version_for({"serializer_version": SERIALIZER_V1}) == SERIALIZER_V1


def test_explicit_v2_resolves_to_v2():
    assert _trainer().serializer_version_for({"serializer_version": SERIALIZER_V2}) == SERIALIZER_V2


def test_unknown_serializer_version_fails_closed():
    with pytest.raises(ValueError, match="unknown serializer_version"):
        _trainer().serializer_version_for({"serializer_version": "semantic-plan-v9"})


def test_selection_does_not_depend_on_experiment_id():
    trainer = _trainer()
    for experiment_id in ("personal-style-b-v1", "personal-style-c-v1", "personal-style-d-v1"):
        assert trainer.serializer_version_for({"experiment_id": experiment_id}) == SERIALIZER_V1


def test_v1_rendering_is_unchanged_by_the_selection_layer():
    trainer = _trainer()
    row = compile_row(_packet(), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V1)
    example = parse_example(json.loads(json.dumps(row)))

    assert trainer.render_prompt_for(example, SERIALIZER_V1) == trainer.render_semantic_prompt(example)


def test_v2_rendering_uses_the_compiled_function_not_a_reconstruction():
    trainer = _trainer()
    row = compile_row(_packet("persuade"), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V2)
    example = parse_example(json.loads(json.dumps(row)))

    out = trainer.render_prompt_for(example, SERIALIZER_V2)

    assert "RHETORICAL FUNCTION\npersuade" in out


def test_v2_rendering_omits_the_function_when_the_row_lacks_it():
    trainer = _trainer()
    row = compile_row(
        _packet(include_function=False), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V2
    )
    example = parse_example(json.loads(json.dumps(row)))

    assert "RHETORICAL FUNCTION" not in trainer.render_prompt_for(example, SERIALIZER_V2)


def test_v1_rendering_ignores_a_present_function():
    """A v2 row rendered under v1 must still produce the v1 layout."""

    trainer = _trainer()
    row = compile_row(_packet("explain"), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V2)
    example = parse_example(json.loads(json.dumps(row)))

    out = trainer.render_prompt_for(example, SERIALIZER_V1)

    assert "RHETORICAL FUNCTION" not in out
    assert "Content atoms:" in out
    assert out.index("Content atoms:") < out.index("Required qualifications:")


def test_build_training_rows_defaults_to_v1():
    trainer = _trainer()
    row = compile_row(_packet(), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V2)
    example = parse_example(json.loads(json.dumps(row)))

    built = trainer.build_training_rows([example])

    assert "NON-NEGOTIABLE" not in built[0]["prompt"][0]["content"]


def test_build_training_rows_honours_v2():
    trainer = _trainer()
    row = compile_row(_packet(), annotation_digest=DIGEST, row_schema=ROW_SCHEMA_V2)
    example = parse_example(json.loads(json.dumps(row)))

    built = trainer.build_training_rows([example], serializer_version=SERIALIZER_V2)

    assert "NON-NEGOTIABLE MEANING CONSTRAINTS" in built[0]["prompt"][0]["content"]
