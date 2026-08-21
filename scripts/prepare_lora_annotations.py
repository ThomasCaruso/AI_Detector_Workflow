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
    load_source_registry,
    prepare_annotation_packets,
    validate_source_registry,
    write_annotation_packets,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare leakage-safe semantic-plan annotation packets from raw human excerpts."
    )
    parser.add_argument("raw_jsonl", type=Path)
    parser.add_argument("source_registry", type=Path)
    parser.add_argument("out_dir", type=Path)
    parser.add_argument("--split-seed", default=DEFAULT_SPLIT_SEED)
    args = parser.parse_args()

    sources = load_source_registry(args.source_registry)
    registry_report = validate_source_registry(sources)
    if not registry_report.valid:
        print(json.dumps(registry_report.to_dict(), indent=2))
        return 2

    excerpts = load_raw_excerpts(args.raw_jsonl)
    packets, report = prepare_annotation_packets(
        excerpts,
        sources,
        split_seed=args.split_seed,
    )
    print(json.dumps(report.to_dict(), indent=2))
    if not report.valid:
        return 2

    written = write_annotation_packets(packets, args.out_dir)
    frozen_manifest = write_frozen_manifest(packets, args.out_dir)
    print(f"written_packets={len(written)}")
    print(f"frozen_manifest={frozen_manifest}")
    print(f"out_dir={args.out_dir}")
    print(
        "Fill content_atoms, immutable_details, required_qualifications, then set "
        "metadata.annotation_status to 'ready'. The frozen manifest prevents target, "
        "instruction, split, genre, or provenance from changing after preparation."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
