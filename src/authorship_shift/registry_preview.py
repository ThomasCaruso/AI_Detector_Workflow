from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .corpus_pipeline import SourceRecord


def planning_source_records(
    records: Iterable[SourceRecord],
    *,
    include_candidates: bool = False,
) -> tuple[list[SourceRecord], list[str]]:
    """Return records eligible for split planning without changing approval state.

    The decision-grade splitter deliberately accepts only ``status=approved``
    sources. During registry construction we still need to preview whether an
    all-candidate registry would produce the intended genre x split matrix before
    doing rights review or annotation work.

    Candidate records are therefore promoted only in this in-memory copy. The
    original ``SourceRecord`` objects are untouched, rejected records are never
    included, and no annotation/training path imports this helper.
    """

    planning: list[SourceRecord] = []
    promoted: list[str] = []
    for row in records:
        if row.status == "approved":
            planning.append(row)
        elif include_candidates and row.status == "candidate":
            planning.append(replace(row, status="approved"))
            promoted.append(row.source_id)
    return planning, sorted(promoted)
