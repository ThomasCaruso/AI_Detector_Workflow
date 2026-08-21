from collections import Counter

from authorship_shift.corpus_pipeline import (
    DEFAULT_TARGET_GENRES,
    SourceRecord,
    deterministic_stratified_splits,
    parse_source_record,
)
from authorship_shift.registry_preview import (
    build_candidate_registry_payload,
    planning_source_records,
)


def _source(source_id: str, *, status: str) -> SourceRecord:
    return SourceRecord(
        source_id=source_id,
        title="Candidate document",
        genre="science_summary",
        status=status,
        provenance_kind="public_domain",
        rights_basis="" if status == "candidate" else "Reviewed source",
    )


def test_candidate_preview_promotes_only_in_memory():
    candidate = _source("candidate-a", status="candidate")
    approved = _source("approved-a", status="approved")
    rejected = _source("rejected-a", status="rejected")

    planning, promoted = planning_source_records(
        [candidate, approved, rejected],
        include_candidates=True,
    )

    assert candidate.status == "candidate"
    assert approved.status == "approved"
    assert rejected.status == "rejected"
    assert {row.source_id for row in planning} == {"candidate-a", "approved-a"}
    assert all(row.status == "approved" for row in planning)
    assert promoted == ["candidate-a"]


def test_approved_only_planning_does_not_include_candidates():
    planning, promoted = planning_source_records(
        [_source("candidate-a", status="candidate"), _source("approved-a", status="approved")],
        include_candidates=False,
    )
    assert [row.source_id for row in planning] == ["approved-a"]
    assert promoted == []


def test_default_registry_skeleton_has_six_candidates_per_target_genre():
    payload = build_candidate_registry_payload()
    rows = [parse_source_record(item) for item in payload["sources"]]

    assert len(rows) == 30
    assert all(row.status == "candidate" for row in rows)
    assert Counter(row.genre for row in rows) == Counter(
        {genre: 6 for genre in DEFAULT_TARGET_GENRES}
    )

    preview, promoted = planning_source_records(rows, include_candidates=True)
    assignments = deterministic_stratified_splits(preview)
    matrix = {
        genre: Counter(
            assignments[row.source_id]
            for row in preview
            if row.genre == genre
        )
        for genre in DEFAULT_TARGET_GENRES
    }
    assert len(promoted) == 30
    for genre in DEFAULT_TARGET_GENRES:
        assert matrix[genre] == Counter({"train": 4, "dev": 1, "holdout": 1})


def test_registry_builder_refuses_too_few_slots_per_genre():
    try:
        build_candidate_registry_payload(slots_per_genre=2)
    except ValueError as exc:
        assert "at least 3" in str(exc)
    else:
        raise AssertionError("two slots per genre cannot cover train/dev/holdout")
