from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.hyphenation_review import suggest_linebreak_hyphenation
from authorship_shift.text_derivation import PageText, load_canonical_extraction


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Review PDF line-break hyphens using same-document orthographic evidence."
    )
    parser.add_argument("canonical_extraction", type=Path)
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    payload, errors = load_canonical_extraction(args.canonical_extraction)
    if errors or payload is None:
        print(json.dumps({"valid": False, "errors": errors}, indent=2))
        return 2

    pages = [PageText(page=int(row["page"]), text=str(row["text"])) for row in payload["pages"]]
    suggestions = suggest_linebreak_hyphenation(pages)
    counts = {name: 0 for name in ("JOIN", "KEEP", "CONFLICT", "UNRESOLVED")}
    for item in suggestions:
        counts[item.verdict] += 1

    result = {
        "valid": True,
        "source_id": payload.get("source_id"),
        "artifact_sha256": payload.get("artifact_sha256"),
        "canonical_text_sha256": payload.get("canonical_text_sha256"),
        "suggestion_count": len(suggestions),
        "verdict_counts": counts,
        "advisory_only": True,
        "suggestions": [item.to_dict() for item in suggestions],
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote={args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
