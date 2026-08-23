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


def _parse_page_spec(value: str | None) -> set[int] | None:
    if value is None:
        return None
    pages: set[int] = set()
    for raw_part in value.split(","):
        part = raw_part.strip()
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            if start < 1 or end < start:
                raise ValueError(f"invalid page range {part!r}")
            pages.update(range(start, end + 1))
        else:
            page = int(part)
            if page < 1:
                raise ValueError("page numbers must be positive")
            pages.add(page)
    if not pages:
        raise ValueError("--pages must select at least one page")
    return pages


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Review PDF line-break hyphens using same-document orthographic evidence."
    )
    parser.add_argument("canonical_extraction", type=Path)
    parser.add_argument(
        "--pages",
        default=None,
        help=(
            "Optional review-page subset such as '3,5-9,12'. Evidence is still gathered "
            "from the full document; only emitted suggestions are filtered."
        ),
    )
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    try:
        selected_pages = _parse_page_spec(args.pages)
    except ValueError as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, indent=2))
        return 2

    payload, errors = load_canonical_extraction(args.canonical_extraction)
    if errors or payload is None:
        print(json.dumps({"valid": False, "errors": errors}, indent=2))
        return 2

    pages = [PageText(page=int(row["page"]), text=str(row["text"])) for row in payload["pages"]]
    all_suggestions = suggest_linebreak_hyphenation(pages)
    suggestions = (
        [item for item in all_suggestions if item.page in selected_pages]
        if selected_pages is not None
        else all_suggestions
    )
    counts = {name: 0 for name in ("JOIN", "KEEP", "CONFLICT", "UNRESOLVED")}
    for item in suggestions:
        counts[item.verdict] += 1

    result = {
        "valid": True,
        "source_id": payload.get("source_id"),
        "artifact_sha256": payload.get("artifact_sha256"),
        "canonical_text_sha256": payload.get("canonical_text_sha256"),
        "review_pages": sorted(selected_pages) if selected_pages is not None else None,
        "evidence_scope": "full_document",
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