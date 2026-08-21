import json

import pytest

from authorship_shift.corpus_pipeline import (
    DEFAULT_TARGET_GENRES,
    RawExcerpt,
    SourceRecord,
    deterministic_split,
    deterministic_stratified_splits,
    load_completed_annotations,
    prepare_annotation_packet,
    prepare_annotation_packets,
    split_assignment_sha256,
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


def _full_registry(documents_per_genre=6):
    return [
        _source(f"{genre}-{index}", genre=genre)
        for genre in DEFAULT_TARGET_GENRES
        for index in range(documents_per_genre)
    ]


def test_legacy_split_is_deterministic_and_source_level():
    first = deterministic_split("document-123")
    second = deterministic_split("document-123")
    assert first == second
    assert first in {"train", "dev", "holdout"}


def test_legacy_split_changes_only_when_seed_or_source_changes():
    a = deterministic_split("document-123", seed="seed-a")
    assert a == deterministic_split("document-123", seed="seed-a")
    values = {
        deterministic_split(f"document-{index}", seed="seed-a")
        for index in range(100)
    }
    assert values == {"train", "dev", "holdout"}


def test_stratified_split_guarantees_every_genre_has_all_three_splits():
    sources = _full_registry(documents_per_genre=6)
    assignments = deterministic_stratified_splits(sources)

    for genre in DEFAULT_TARGET_GENRES:
        genre_sources = [row.source_id for row in sources if row.genre == genre]
        counts = {
            split: sum(assignments[source_id] == split for source_id in genre_sources)
            for split in ("train", "dev", "holdout")
        }
        assert counts == {"train": 4, "dev": 1, "holdout": 1}


def test_stratified_split_is_deterministic_for_registry_and_seed():
    sources = _full_registry(documents_per_genre=10)
    first = deterministic_stratified_splits(sources, seed="seed-a")
    second = deterministic_stratified_splits(list(reversed(sources)), seed="seed-a")
    assert first == second
    assert split_assignment_sha256(sources, first, seed="seed-a") == split_assignment_sha256(
        list(reversed(sources)), second, seed="seed-a"
    )


def test_stratified_split_refuses_thin_or_missing_target_genres():
    sources = [_source("science-a"), _source("science-b")]
    with pytest.raises(ValueError, match="at least 3 approved source documents") as exc:
        deterministic_stratified_splits(sources)
    message = str(exc.value)
    assert "science_summary=2" in message
    assert "business_analysis=0" in message


def test_diagnostic_stratification_can_opt_out_for_tiny_fixture():
    source = _source()
    assignments = deterministic_stratified_splits(
        [source],
        require_genre_coverage=False,
    )
    assert assignments[source.source_id] in {"train", "dev", "holdout"}


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


def test_all_excerpts_from_same_source_receive_same_stratified_split():
    sources = _full_registry(documents_per_genre=6)
    source = next(row for row in sources if row.genre == "science_summary")
    packets, report = prepare_annotation_packets(
        [
            _excerpt(source_id=source.source_id, excerpt_id="a"),
            _excerpt(source_id=source.source_id, excerpt_id="b"),
        ],
        sources,
    )
    assert report.valid
    assert len(packets) == 2
    assert len({packet["split"] for packet in packets}) == 1
    assert all(packet["metadata"]["split_strategy"] == "genre-stratified-hash-v1" for packet in packets)
    assert all(packet["metadata"]["registry_split_sha256"] == report.registry_split_sha256 for packet in packets)


def test_preparation_report_exposes_source_level_genre_matrix():
    sources = _full_registry(documents_per_genre=6)
    source = next(row for row in sources if row.genre == "science_summary")
    packets, report = prepare_annotation_packets(
        [_excerpt(source_id=source.source_id)],
        sources,
    )
    assert report.valid
    assert len(packets) == 1
    for genre in DEFAULT_TARGET_GENRES:
        assert report.genre_split_source_counts[genre] == {
            "train": 4,
            "dev": 1,
            "holdout": 1,
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
