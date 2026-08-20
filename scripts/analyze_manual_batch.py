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


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyze completed outputs from an Engine v2 manual candidate batch."
    )
    parser.add_argument("batch", type=Path, help="Batch directory created by prepare_manual_batch.py")
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Analyze available outputs even when some expected files are missing",
    )
    args = parser.parse_args()

    manifest_path = args.batch / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest["source"]

    candidates: list[tuple[str, str]] = []
    missing: list[str] = []
    for profile in manifest.get("profiles", []):
        relative = profile["expected_output_file"]
        path = args.batch / relative
        if not path.exists():
            missing.append(relative)
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            missing.append(relative)
            continue
        candidates.append((profile["name"], text))

    if missing and not args.allow_partial:
        joined = "\n- ".join(missing)
        raise RuntimeError(
            "manual batch is incomplete; missing or empty outputs:\n- " + joined
        )
    if not candidates:
        raise RuntimeError("manual batch contains no completed candidate outputs")

    analyses = analyze_candidates(source, candidates)
    payload = {
        "case_id": manifest.get("case_id"),
        "candidate_count": len(candidates),
        "missing_outputs": missing,
        "analyses": [row.to_dict() for row in analyses],
    }
    output_path = args.batch / "analysis.json"
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"case={manifest.get('case_id')} candidates={len(candidates)}")
    for row in analyses:
        print(
            f"{row.candidate_id}: "
            f"pair_dist={row.mean_pairwise_distance:.3f} "
            f"source_3gram={row.source_trigram_overlap:.3f} "
            f"opening_repeat={row.opening_repeat_ratio:.3f} "
            f"immutables={row.immutable_coverage:.3f}"
        )
    if missing:
        print(f"missing_outputs={len(missing)}")
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
