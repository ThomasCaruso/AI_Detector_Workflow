from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.semantic_plan import render_plan_extraction_prompt


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render semantic-plan extraction prompts for pending annotation packets."
    )
    parser.add_argument("annotations_dir", type=Path)
    parser.add_argument("out_dir", type=Path)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict] = []
    count = 0

    for packet_path in sorted(args.annotations_dir.glob("*.json")):
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        metadata = packet.get("metadata", {})
        status = metadata.get("annotation_status") if isinstance(metadata, dict) else None
        if status != "pending":
            continue

        prompt_path = args.out_dir / f"{packet['id']}.md"
        response_path = args.out_dir / f"{packet['id']}.response.json"
        prompt_path.write_text(render_plan_extraction_prompt(packet), encoding="utf-8")
        manifest.append(
            {
                "id": packet["id"],
                "packet_file": str(packet_path),
                "prompt_file": str(prompt_path),
                "response_file": str(response_path),
            }
        )
        count += 1

    (args.out_dir / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "items": manifest}, indent=2),
        encoding="utf-8",
    )
    print(f"prepared_prompts={count}")
    print(f"out_dir={args.out_dir}")
    print(
        "Run each prompt independently if desired and save JSON only to the matching "
        "*.response.json file. Ingested suggestions remain needs_review until a human approves them."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
