from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.text_derivation import (
    EXTRACTOR_VERSION,
    PageText,
    apply_reviewed_corrections,
    normalize_pdf_text,
    sha256_file,
    write_canonical_extraction,
)


def _require_pinned_pypdf() -> None:
    try:
        installed = version("pypdf")
    except PackageNotFoundError as exc:
        raise RuntimeError(
            "pypdf is not installed; install research/lora/extraction-requirements.txt"
        ) from exc
    if installed != EXTRACTOR_VERSION:
        raise RuntimeError(
            f"pypdf version drift: expected {EXTRACTOR_VERSION}, found {installed}; "
            "use research/lora/extraction-requirements.txt"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract canonical, reproducible page text from a frozen PDF artifact."
    )
    parser.add_argument("artifact", type=Path)
    parser.add_argument("out_json", type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument(
        "--corrections",
        type=Path,
        default=None,
        help="Optional reviewed page-scoped correction ledger JSON.",
    )
    args = parser.parse_args()

    try:
        _require_pinned_pypdf()
        from pypdf import PdfReader

        artifact_hash = sha256_file(args.artifact)
        reader = PdfReader(str(args.artifact))
        base_pages = [
            PageText(
                page=index,
                text=normalize_pdf_text(
                    page.extract_text(extraction_mode="plain") or ""
                ),
            )
            for index, page in enumerate(reader.pages, start=1)
        ]

        correction_payload = None
        if args.corrections is not None:
            correction_payload = json.loads(
                args.corrections.read_text(encoding="utf-8-sig")
            )
            if not isinstance(correction_payload, dict):
                raise ValueError("corrections file must contain a JSON object")

        canonical_pages, correction_hash = apply_reviewed_corrections(
            base_pages,
            correction_payload,
            artifact_sha256=artifact_hash,
        )
        payload = write_canonical_extraction(
            args.out_json,
            source_id=args.source_id,
            artifact_sha256=artifact_hash,
            base_pages=base_pages,
            canonical_pages=canonical_pages,
            correction_hash=correction_hash,
        )
    except (OSError, UnicodeError, ValueError, RuntimeError) as exc:
        print(json.dumps({"valid": False, "error": str(exc)}, indent=2))
        return 2

    summary = {key: value for key, value in payload.items() if key != "pages"}
    summary["page_count"] = len(payload["pages"])
    summary["out_json"] = str(args.out_json)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
