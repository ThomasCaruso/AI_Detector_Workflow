from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.corpus_pipeline import (
    DEFAULT_SPLIT_SEED,
    DEFAULT_TARGET_GENRES,
    SPLIT_STRATEGY,
    TARGET_SPLITS,
    deterministic_stratified_splits,
    split_assignment_sha256,
    validate_source_registry,
)
from authorship_shift.registry_io import load_source_registry_safe
from authorship_shift.registry_preview import planning_source_records
from authorship_shift.source_snapshot import (
    load_registry_snapshots,
    snapshot_set_sha256,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan deterministic genre-stratified source splits before collecting or annotating prose."
    )
    parser.add_argument("source_registry", type=Path)
    parser.add_argument("--split-seed", default=DEFAULT_SPLIT_SEED)
    parser.add_argument(
        "--include-candidates",
        action="store_true",
        help=(
            "Planning-only preview: temporarily treat candidate sources as eligible for "
            "split assignment without changing their registry status. Annotation and "
            "training still require approved sources."
        ),
    )
    parser.add_argument(
        "--allow-incomplete-genre-coverage",
        action="store_true",
        help="Diagnostic escape hatch for an unfinished registry.",
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    snapshots, snapshot_errors = load_registry_snapshots(args.source_registry)
    if snapshot_errors:
        print(json.dumps({"valid": False, "source_snapshot_errors": snapshot_errors}, indent=2))
        return 2

    sources, registry_parse_errors = load_source_registry_safe(args.source_registry)
    if registry_parse_errors:
        print(json.dumps({"valid": False, "registry_parse_errors": registry_parse_errors}, indent=2))
        return 2

    registry_report = validate_source_registry(sources)
    if not registry_report.valid:
        print(json.dumps(registry_report.to_dict(), indent=2))
        return 2

    planning_sources, promoted_candidates = planning_source_records(
        sources,
        include_candidates=args.include_candidates,
    )
    try:
        assignments = deterministic_stratified_splits(
            planning_sources,
            seed=args.split_seed,
            require_genre_coverage=not args.allow_incomplete_genre_coverage,
        )
    except ValueError as exc:
        payload = {
            "valid": False,
            "planning_mode": "candidate_preview" if args.include_candidates else "approved_only",
            "split_seed": args.split_seed,
            "error": str(exc),
        }
        print(json.dumps(payload, indent=2))
        return 3

    eligible = {
        row.source_id: row
        for row in planning_sources
        if row.status == "approved"
    }
    matrix = {
        genre: {split: 0 for split in TARGET_SPLITS}
        for genre in DEFAULT_TARGET_GENRES
    }
    extra_genres: dict[str, dict[str, int]] = {}
    for source_id, split in assignments.items():
        genre = eligible[source_id].genre
        if genre not in matrix:
            extra_genres.setdefault(genre, {name: 0 for name in TARGET_SPLITS})
            extra_genres[genre][split] += 1
        else:
            matrix[genre][split] += 1

    fingerprint = split_assignment_sha256(
        planning_sources,
        assignments,
        seed=args.split_seed,
    )
    preview = bool(promoted_candidates)
    payload = {
        "valid": True,
        "planning_mode": "candidate_preview" if preview else "approved_only",
        "split_seed": args.split_seed,
        "split_strategy": SPLIT_STRATEGY,
        "registry_split_sha256": None if preview else fingerprint,
        "preview_split_sha256": fingerprint if preview else None,
        "source_snapshot_set_sha256": snapshot_set_sha256(snapshots),
        "snapshotted_approved_sources": len(snapshots),
        "approved_sources": sum(1 for row in sources if row.status == "approved"),
        "candidate_sources_in_preview": len(promoted_candidates),
        "promoted_candidate_source_ids": promoted_candidates,
        "eligible_planning_sources": len(assignments),
        "target_genre_source_matrix": matrix,
        "extra_genre_source_matrix": extra_genres,
        "assignments": dict(sorted(assignments.items())),
        "warning": (
            "Preview only: candidate sources remain unapproved. This fingerprint is not a "
            "frozen training split contract; run again without --include-candidates after "
            "rights review, exact-artifact snapshotting, and approval."
            if preview
            else None
        ),
    }
    print(json.dumps(payload, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote={args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
