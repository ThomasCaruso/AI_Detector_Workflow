from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.corpus_audit import audit_corpus
from authorship_shift.corpus_pipeline import DEFAULT_TARGET_GENRES
from authorship_shift.lora_data import load_jsonl, validate_dataset


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit LoRA corpus balance, genre/split coverage, source concentration, and near-duplicate targets."
    )
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--near-duplicate-threshold", type=float, default=0.80)
    parser.add_argument("--max-source-share", type=float, default=0.15)
    parser.add_argument("--min-genre-examples", type=int, default=5)
    parser.add_argument("--json-out", type=Path, default=None)
    parser.add_argument(
        "--allow-incomplete-genre-coverage",
        action="store_true",
        help="Diagnostic escape hatch; decision-grade audits require every target genre in train/dev/holdout.",
    )
    args = parser.parse_args()

    examples = load_jsonl(args.dataset)
    validation = validate_dataset(examples)
    if not validation.valid:
        print(json.dumps(validation.to_dict(), indent=2))
        return 2

    report = audit_corpus(
        examples,
        near_duplicate_threshold=args.near_duplicate_threshold,
        max_source_share=args.max_source_share,
        min_genre_examples=args.min_genre_examples,
        expected_genres=DEFAULT_TARGET_GENRES,
    )
    payload = report.to_dict()
    print(json.dumps(payload, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"wrote={args.json_out}")

    if not report.genre_split_coverage_ok and not args.allow_incomplete_genre_coverage:
        print("decision_grade_genre_split_coverage=false")
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
