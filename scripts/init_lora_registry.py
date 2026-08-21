from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.registry_preview import build_candidate_registry_payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a balanced local candidate source registry for LoRA corpus planning."
    )
    parser.add_argument("out_json", type=Path)
    parser.add_argument("--slots-per-genre", type=int, default=6)
    parser.add_argument(
        "--placeholder-provenance-kind",
        default="public_domain",
        choices=["public_domain", "licensed", "user_owned", "consented"],
        help=(
            "Provisional placeholder only. Each candidate's provenance must be verified "
            "or replaced before approval."
        ),
    )
    args = parser.parse_args()

    if args.out_json.exists():
        raise SystemExit(
            f"refusing to overwrite existing registry: {args.out_json}; choose a new path or remove it explicitly"
        )

    payload = build_candidate_registry_payload(
        slots_per_genre=args.slots_per_genre,
        placeholder_provenance_kind=args.placeholder_provenance_kind,
    )
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"wrote={args.out_json}")
    print(f"candidate_sources={len(payload['sources'])}")
    print(f"slots_per_genre={args.slots_per_genre}")
    print("all_sources_status=candidate")
    print(
        "Next: replace each placeholder with one exact document, review rights/provenance, "
        "and use plan_lora_splits.py --include-candidates to preview the split matrix."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
