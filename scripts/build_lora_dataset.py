from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.annotation_integrity import verify_frozen_manifest
from authorship_shift.corpus_pipeline import load_completed_annotations, write_training_jsonl
from authorship_shift.lora_data import validate_dataset


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compile ready semantic-plan annotations into validated LoRA JSONL."
    )
    parser.add_argument("annotations_dir", type=Path)
    parser.add_argument("out_jsonl", type=Path)
    parser.add_argument(
        "--require-trainable",
        action="store_true",
        help="Require non-empty train, dev, and holdout splits before writing.",
    )
    args = parser.parse_args()

    integrity_errors = verify_frozen_manifest(args.annotations_dir)
    if integrity_errors:
        print(json.dumps({"frozen_contract_valid": False, "errors": integrity_errors}, indent=2))
        return 4

    examples = load_completed_annotations(args.annotations_dir)
    report = validate_dataset(examples)
    print(json.dumps(report.to_dict(), indent=2))
    if not report.valid:
        return 2

    if args.require_trainable:
        missing = [split for split, count in report.split_counts.items() if count == 0]
        if missing:
            print(f"missing_required_splits={','.join(missing)}")
            return 3

    write_training_jsonl(examples, args.out_jsonl)
    print(f"wrote={args.out_jsonl}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
