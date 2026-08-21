from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from .corpus_pipeline import DEFAULT_TARGET_GENRES, SourceRecord


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


def build_candidate_registry_payload(
    *,
    slots_per_genre: int = 6,
    placeholder_provenance_kind: str = "public_domain",
) -> dict:
    """Build a local registry skeleton with evenly distributed candidate slots.

    ``provenance_kind`` is explicitly provisional in these slots. It exists only
    because the registry schema requires a known provenance category; every slot
    remains ``status=candidate`` and therefore cannot enter annotation or training
    until the exact document's rights basis is reviewed and the field is verified
    or replaced.

    Generated ``source_id`` values are slot identifiers only. When a real document
    is chosen, replace the placeholder ID with a stable document-specific ID so the
    split fingerprint tracks document identity rather than an abstract slot.
    """

    if slots_per_genre < 3:
        raise ValueError("slots_per_genre must be at least 3 for train/dev/holdout coverage")

    prefixes = {
        "business_analysis": "biz",
        "technical_explanation": "tech",
        "science_summary": "science",
        "professional_writing": "pro",
        "analytical_argument": "arg",
    }
    sources: list[dict] = []
    for genre in DEFAULT_TARGET_GENRES:
        prefix = prefixes.get(genre, genre.replace("_", "-")[:12])
        for index in range(1, slots_per_genre + 1):
            sources.append(
                {
                    "source_id": f"candidate-{prefix}-{index:02d}",
                    "title": f"TODO exact {genre.replace('_', ' ')} document {index:02d}",
                    "genre": genre,
                    "status": "candidate",
                    "provenance_kind": placeholder_provenance_kind,
                    "rights_basis": "",
                    "canonical_url": None,
                    "author_or_agency": None,
                    "license": None,
                    "document_locator": None,
                    "notes": (
                        "Placeholder slot only. Replace source_id with a stable ID for the "
                        "exact document; verify or replace provenance_kind; then fill title, "
                        "URL/locator, rights basis, and third-party-material review before "
                        "changing status to approved."
                    ),
                }
            )
    return {
        "schema_version": 1,
        "template_note": (
            f"{len(sources)} candidate slots: {slots_per_genre} per target genre. "
            "All records are intentionally unapproved. source_id and provenance_kind are "
            "placeholders until exact-document selection and rights review."
        ),
        "sources": sources,
    }
