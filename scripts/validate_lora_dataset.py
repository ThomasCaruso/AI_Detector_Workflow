from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.lora_data import load_jsonl, validate_dataset


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate an AuthorshipShift LoRA JSONL corpus without loading a model."
    )
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()

    examples = load_jsonl(args.dataset)
    report = validate_dataset(examples)

    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"examples={report.example_count} valid={str(report.valid).lower()}")
        print(
            "splits="
            + ", ".join(f"{name}:{count}" for name, count in report.split_counts.items())
        )
        if report.errors:
            print("errors:")
            for item in report.errors:
                print(f"- {item}")
        if report.warnings:
            print("warnings:")
            for item in report.warnings:
                print(f"- {item}")

    return 0 if report.valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
