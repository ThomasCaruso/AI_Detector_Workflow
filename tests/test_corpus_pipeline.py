import json

import pytest

from authorship_shift.corpus_pipeline import (
    RawExcerpt,
    SourceRecord,
    deterministic_split,
    load_completed_annotations,
    prepare_annotation_packet,
    prepare_annotation_packets,
    validate_source_registry,
    write_annotation_packets,
    write_training_jsonl,
)


def _source(source_id="source-a", *, status="approved", genre="science_summary"):
    return SourceRecord(
        source_id=source_id,
        title="Human-authored source",
        genre=genre,
        status=status,
        provenance_kind="public_domain",
        rights_basis="Verified agency-authored U.S. Government work; no third-party passage used.",
        canonical_url="https://example.gov/document",
        author_or_agency="Example Agency",
        license="Public Domain (U.S. Government work)",
    )


def _excerpt(source_id="source-a", *, excerpt_id="ex-1", genre="science_summary"):
    return RawExcerpt(
        id=excerpt_id,
        source_id=source_id,
        genre=genre,
        instruction="Explain the finding in clear analytical prose.",
        target_text=(
            "Measurements taken over several seasons showed a persistent difference between "
            "the two sites, although the observational design did not establish the cause. "
            "The report separates the measured pattern from the mechanisms that might explain it."
        ),
        excerpt_locator="pp. 4-5",
    )


def test_split_is_deterministic_and_source_level():
    first = deterministic_split("document-123")
    second = deterministic_split("document-123")
    assert first == second
    assert first in {"train", "dev", "holdout"}


def test_split_changes_only_when_seed_or_source_changes():
    # The exact buckets are deliberately not pinned; the invariant is that the
    # mapping is a pure function of source_id + frozen seed.
    a = deterministic_split("document-123", seed="seed-a")
    assert a == deterministic_split("document-123", seed="seed-a")
    values = {
        deterministic_split(f"document-{index}", seed="seed-a")
        for index in range(100)
    }
    assert values == {"train", "dev", "holdout"}


def test_unapproved_source_cannot_prepare_training_packet():
    with pytest.raises(ValueError, match="not approved"):
        prepare_annotation_packet(_excerpt(), _source(status="candidate"))


def test_genre_mismatch_is_rejected():
    with pytest.raises(ValueError, match="genre"):
        prepare_annotation_packet(
            _excerpt(genre="science_summary"),
            _source(genre="business_analysis"),
        )


def test_annotation_packet_starts_with_empty_semantic_plan():
    packet = prepare_annotation_packet(_excerpt(), _source())
    assert packet["content_atoms"] == []
    assert packet["immutable_details"] == []
    assert packet["required_qualifications"] == []
    assert packet["target_text"] == _excerpt().target_text
    assert packet["metadata"]["annotation_status"] == "pending"
    assert packet["metadata"]["target_sha256"]
    assert packet["provenance"]["source_id"] == "source-a"


def test_all_excerpts_from_same_source_receive_same_split():
    source = _source()
    packets, report = prepare_annotation_packets(
        [_excerpt(excerpt_id="a"), _excerpt(excerpt_id="b")],
        [source],
    )
    assert report.valid
    assert len(packets) == 2
    assert {packet["split"] for packet in packets} == {
        deterministic_split(source.source_id)
    }


def test_registry_flags_duplicate_ids():
    report = validate_source_registry([_source(), _source()])
    assert not report.valid
    assert any("duplicate source_id" in error for error in report.errors)


def test_annotation_writer_refuses_to_overwrite(tmp_path):
    packet = prepare_annotation_packet(_excerpt(), _source())
    paths = write_annotation_packets([packet], tmp_path)
    assert len(paths) == 1
    with pytest.raises(FileExistsError, match="do not silently overwrite"):
        write_annotation_packets([packet], tmp_path)


def test_only_ready_annotations_are_compiled(tmp_path):
    pending = prepare_annotation_packet(_excerpt(excerpt_id="pending"), _source())
    ready = prepare_annotation_packet(_excerpt(excerpt_id="ready"), _source())
    ready["content_atoms"] = ["seasonal measurements differed", "cause was not established"]
    ready["immutable_details"] = []
    ready["required_qualifications"] = ["observational pattern is not causal evidence"]
    ready["metadata"]["annotation_status"] = "ready"

    (tmp_path / "pending.json").write_text(json.dumps(pending), encoding="utf-8")
    (tmp_path / "ready.json").write_text(json.dumps(ready), encoding="utf-8")

    rows = load_completed_annotations(tmp_path)
    assert [row.id for row in rows] == ["ready"]


def test_dataset_writer_reuses_leakage_validator(tmp_path):
    packet = prepare_annotation_packet(_excerpt(excerpt_id="ready"), _source())
    packet["content_atoms"] = [
        "Measurements taken over several seasons showed a persistent difference between the two sites, although",
        "cause was not established",
    ]
    packet["required_qualifications"] = []
    packet["metadata"]["annotation_status"] = "ready"
    (tmp_path / "ready.json").write_text(json.dumps(packet), encoding="utf-8")

    rows = load_completed_annotations(tmp_path)
    with pytest.raises(ValueError, match="dataset validation failed"):
        write_training_jsonl(rows, tmp_path / "train.jsonl")
