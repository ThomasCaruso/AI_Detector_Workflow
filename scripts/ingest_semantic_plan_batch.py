from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.semantic_plan import apply_plan_draft, parse_plan_response


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest semantic-plan JSON suggestions into local annotation packets."
    )
    parser.add_argument("batch_dir", type=Path)
    args = parser.parse_args()

    manifest_path = args.batch_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    applied = 0
    missing = 0

    for item in manifest.get("items", []):
        response_path = Path(item["response_file"])
        if not response_path.exists() or not response_path.read_text(encoding="utf-8").strip():
            missing += 1
            continue

        packet_path = Path(item["packet_file"])
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        before_target = packet.get("target_text")
        before_split = packet.get("split")
        before_provenance = packet.get("provenance")

        draft = parse_plan_response(response_path.read_text(encoding="utf-8"))
        updated = apply_plan_draft(packet, draft)

        # Frozen fields are asserted again at the I/O boundary so even a future
        # helper regression cannot silently let the extractor rewrite the target.
        if updated.get("target_text") != before_target:
            raise RuntimeError(f"{item['id']}: target_text changed during plan ingestion")
        if updated.get("split") != before_split:
            raise RuntimeError(f"{item['id']}: split changed during plan ingestion")
        if updated.get("provenance") != before_provenance:
            raise RuntimeError(f"{item['id']}: provenance changed during plan ingestion")

        packet_path.write_text(
            json.dumps(updated, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        applied += 1

    print(f"applied={applied}")
    print(f"missing_responses={missing}")
    print(
        "All ingested packets are needs_review. Inspect semantic sufficiency and leakage, "
        "then manually set metadata.annotation_status='ready' only for approved annotations."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
