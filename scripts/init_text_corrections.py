from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.text_derivation import load_canonical_extraction


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a reviewed-corrections ledger template from a base canonical extraction."
    )
    parser.add_argument("base_extraction", type=Path)
    parser.add_argument("out_json", type=Path)
    args = parser.parse_args()

    payload, errors = load_canonical_extraction(args.base_extraction)
    if errors or payload is None:
        print(json.dumps({"valid": False, "errors": errors}, indent=2))
        return 2
    if payload.get("corrections_sha256") is not None:
        print(
            json.dumps(
                {
                    "valid": False,
                    "error": "base extraction already contains reviewed corrections; initialize from an uncorrected extraction",
                },
                indent=2,
            )
        )
        return 2
    if args.out_json.exists():
        print(json.dumps({"valid": False, "error": f"refusing to overwrite {args.out_json}"}, indent=2))
        return 2

    ledger = {
        "schema_version": 1,
        "artifact_sha256": payload["artifact_sha256"],
        "base_text_sha256": payload["base_text_sha256"],
        "replacements": [],
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(ledger, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"valid": True, "wrote": str(args.out_json)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
