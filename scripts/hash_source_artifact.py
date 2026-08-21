from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Hash an exact source artifact for the LoRA provenance registry."
    )
    parser.add_argument("artifact", type=Path)
    parser.add_argument(
        "--artifact-kind",
        choices=("pdf", "html", "text", "other"),
        required=True,
    )
    parser.add_argument("--revision-label", default=None)
    args = parser.parse_args()

    data = args.artifact.read_bytes()
    payload = {
        "retrieved_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sha256": hashlib.sha256(data).hexdigest(),
        "artifact_kind": args.artifact_kind,
        "revision_label": args.revision_label,
        "byte_count": len(data),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
