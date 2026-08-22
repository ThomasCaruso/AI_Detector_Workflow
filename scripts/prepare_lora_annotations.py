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
from authorship_shift.registry_io import load_source_registry_safe
from authorship_shift.source_snapshot import (
    load_registry_snapshots,
    snapshot_set_sha256,
)


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

    try:
        excerpts = load_raw_excerpts(args.raw_jsonl)
    except (OSError, UnicodeError, ValueError) as exc:
        print(json.dumps({"valid": False, "raw_excerpt_errors": [str(exc)]}, indent=2))
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

    # Snapshot metadata is copied from the reviewed registry into the annotation
    # packet before the frozen manifest is written. It is provenance/audit data,
    # never part of the model prompt.
    for packet in packets:
        source_id = packet["provenance"]["source_id"]
        snapshot = snapshots.get(source_id)
        if snapshot is not None:
            packet.setdefault("metadata", {})["source_snapshot"] = snapshot.to_dict()

    written = write_annotation_packets(packets, args.out_dir)
    frozen_manifest = write_frozen_manifest(packets, args.out_dir)
    print(f"written_packets={len(written)}")
    print(f"frozen_manifest={frozen_manifest}")
    print(f"split_strategy={report.split_strategy}")
    print(f"registry_split_sha256={report.registry_split_sha256}")
    print(f"source_snapshot_set_sha256={snapshot_set_sha256(snapshots)}")
    print(f"out_dir={args.out_dir}")
    print(
        "Fill content_atoms, immutable_details, required_qualifications, then set "
        "metadata.annotation_status to 'ready'. The frozen manifest prevents target, "
        "instruction, split, genre, provenance, or source snapshot from changing after preparation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
