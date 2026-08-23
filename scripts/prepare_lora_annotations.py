from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.annotation_integrity import write_frozen_manifest
from authorship_shift.corpus_pipeline import (
    DEFAULT_SPLIT_SEED,
    load_raw_excerpts,
    prepare_annotation_packets,
    validate_source_registry,
    write_annotation_packets,
)
from authorship_shift.excerpt_dedup import audit_raw_excerpt_duplicates
from authorship_shift.registry_io import load_source_registry_safe
from authorship_shift.source_exclusions import (
    load_registry_source_exclusions,
    validate_excerpt_pages,
)
from authorship_shift.source_snapshot import (
    load_registry_snapshots,
    snapshot_set_sha256,
)
from authorship_shift.text_derivation import load_registry_text_derivations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare leakage-safe, genre-stratified semantic-plan annotation packets."
    )
    parser.add_argument("raw_jsonl", type=Path)
    parser.add_argument("source_registry", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--split-seed", default=DEFAULT_SPLIT_SEED)
    parser.add_argument(
        "--allow-incomplete-genre-coverage",
        action="store_true",
        help=(
            "Diagnostic escape hatch for tiny smoke fixtures. Decision-grade preparation "
            "requires at least three approved source documents in every target genre so "
            "train/dev/holdout are all represented."
        ),
    )
    args = parser.parse_args()

    snapshots, snapshot_errors = load_registry_snapshots(args.source_registry)
    if snapshot_errors:
        print(json.dumps({"source_snapshot_valid": False, "errors": snapshot_errors}, indent=2))
        return 2

    sources, registry_parse_errors = load_source_registry_safe(args.source_registry)
    if registry_parse_errors:
        print(json.dumps({"valid": False, "registry_parse_errors": registry_parse_errors}, indent=2))
        return 2
    registry_report = validate_source_registry(sources)
    if not registry_report.valid:
        print(json.dumps(registry_report.to_dict(), indent=2))
        return 2

    derivations, canonical_pages, derivation_errors = load_registry_text_derivations(
        args.source_registry
    )
    if derivation_errors:
        print(json.dumps({"text_derivation_valid": False, "errors": derivation_errors}, indent=2))
        return 2

    source_exclusions, exclusion_errors = load_registry_source_exclusions(
        args.source_registry
    )
    if exclusion_errors:
        print(json.dumps({"source_exclusions_valid": False, "errors": exclusion_errors}, indent=2))
        return 2

    try:
        excerpts = load_raw_excerpts(args.raw_jsonl)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "raw_excerpt_errors": [str(exc)]}, indent=2))
        return 2

    target_errors: list[str] = []
    for excerpt in excerpts:
        pages = canonical_pages.get(excerpt.source_id)
        if pages is None:
            continue
        try:
            validate_excerpt_pages(
                excerpt,
                pages,
                source_exclusions.get(excerpt.source_id, tuple()),
            )
        except ValueError as exc:
            target_errors.append(str(exc))
    if target_errors:
        print(
            json.dumps(
                {"canonical_target_and_source_pages_valid": False, "errors": target_errors},
                indent=2,
            )
        )
        return 2

    dedup_report = audit_raw_excerpt_duplicates(excerpts)
    if not dedup_report.valid:
        print(
            json.dumps(
                {"raw_excerpt_dedup_valid": False, **dedup_report.to_dict()},
                indent=2,
            )
        )
        return 2

    packets, report = prepare_annotation_packets(
        excerpts,
        sources,
        split_seed=args.split_seed,
        require_genre_coverage=not args.allow_incomplete_genre_coverage,
    )
    print(json.dumps(report.to_dict(), indent=2))
    if not report.valid:
        return 2

    if dedup_report.within_source_near_duplicates:
        print(
            json.dumps(
                {
                    "raw_excerpt_dedup_warning": True,
                    "message": (
                        "near-duplicate raw excerpts were found within the same source; "
                        "they cannot cross source-level train/dev/holdout assignment, but "
                        "review them for accidental repeated extraction or overweighting"
                    ),
                    "within_source_near_duplicates": [
                        row.to_dict()
                        for row in dedup_report.within_source_near_duplicates
                    ],
                },
                indent=2,
            )
        )

    # Snapshot, derivation, and exclusion metadata are copied from the reviewed
    # local registry before the frozen manifest is written. They are audit data,
    # not model-prompt fields. metadata.source_pages originates in raw excerpts.
    for packet in packets:
        source_id = packet["provenance"]["source_id"]
        snapshot = snapshots.get(source_id)
        if snapshot is not None:
            packet.setdefault("metadata", {})["source_snapshot"] = snapshot.to_dict()
        derivation = derivations.get(source_id)
        if derivation is not None:
            packet.setdefault("metadata", {})[
                "source_text_derivation"
            ] = derivation.frozen_dict()
        packet.setdefault("metadata", {})["source_exclusions"] = [
            item.to_dict() for item in source_exclusions.get(source_id, tuple())
        ]

    written = write_annotation_packets(packets, args.out_dir)
    frozen_manifest = write_frozen_manifest(packets, args.out_dir)
    print(f"written_packets={len(written)}")
    print(f"frozen_manifest={frozen_manifest}")
    print(f"split_strategy={report.split_strategy}")
    print(f"registry_split_sha256={report.registry_split_sha256}")
    print(f"source_snapshot_set_sha256={snapshot_set_sha256(snapshots)}")
    print(f"text_derivations={len(derivations)}")
    print(f"sources_with_exclusions={sum(bool(value) for value in source_exclusions.values())}")
    print(f"out_dir={args.out_dir}")
    print(
        "Fill content_atoms, immutable_details, required_qualifications, then set "
        "metadata.annotation_status to 'ready'. The frozen manifest prevents target, "
        "instruction, split, genre, provenance, source pages, source exclusions, "
        "source snapshot, or text derivation from changing after preparation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
