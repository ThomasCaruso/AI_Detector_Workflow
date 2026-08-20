from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.candidate_lab import analyze_candidates


def _load_case(path: Path) -> tuple[str, list[tuple[str, str]], dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    reference = data.get("reference_text") or data.get("source") or ""
    if not reference.strip():
        raise ValueError("case file must contain reference_text or source")

    candidates = []
    metadata = {}
    for item in data.get("candidates", []):
        candidate_id = str(item["id"])
        candidates.append((candidate_id, str(item["text"])))
        metadata[candidate_id] = item.get("external_metadata", {})

    if not candidates:
        raise ValueError("case file contains no candidates")
    return reference, candidates, metadata


def _fmt(value: float) -> str:
    return f"{value:.3f}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze an AuthorshipShift candidate set using deterministic local metrics."
    )
    parser.add_argument("case", type=Path, help="Path to a structured eval JSON file")
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Emit JSON instead of a human-readable table",
    )
    args = parser.parse_args()

    reference, candidates, external = _load_case(args.case)
    analyses = analyze_candidates(reference, candidates)

    if args.as_json:
        payload = []
        for row in analyses:
            item = row.to_dict()
            item["external_metadata"] = external.get(row.candidate_id, {})
            payload.append(item)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    headers = [
        "candidate",
        "words",
        "sent_cv",
        "open_repeat",
        "open_entropy",
        "transition",
        "source_3gram",
        "struct_dist",
        "pair_dist",
        "immutables",
    ]
    print("\t".join(headers))
    for row in analyses:
        print(
            "\t".join(
                [
                    row.candidate_id,
                    str(row.word_count),
                    _fmt(row.sentence_length_cv),
                    _fmt(row.opening_repeat_ratio),
                    _fmt(row.opening_entropy),
                    _fmt(row.transition_start_ratio),
                    _fmt(row.source_trigram_overlap),
                    _fmt(row.structural_distance_from_source),
                    _fmt(row.mean_pairwise_distance),
                    _fmt(row.immutable_coverage),
                ]
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
