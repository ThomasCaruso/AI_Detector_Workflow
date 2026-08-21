from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.batch_gate import assess_batch
from authorship_shift.candidate_lab import analyze_candidates
from authorship_shift.collapse import assess_collapse
from authorship_shift.rerank import rerank


def _manifest_candidates(manifest: dict) -> list[dict]:
    """Return candidate entries from a v2 manifest, or adapt a v1 manifest.

    The v1 layout had exactly one candidate per profile and keyed it by profile
    name, so batches prepared before replicate support still analyze correctly.
    """

    entries = manifest.get("candidates")
    if entries:
        return list(entries)

    adapted = []
    for index, profile in enumerate(manifest.get("profiles", []), start=1):
        adapted.append(
            {
                "candidate_id": profile["name"],
                "profile": profile["name"],
                "profile_index": profile.get("index", index),
                "sample_index": 1,
                "prompt_file": profile.get("prompt_file"),
                "expected_output_file": profile["expected_output_file"],
                "requested_controls": profile.get("requested_controls", {}),
            }
        )
    return adapted


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
    parser.add_argument(
        "--select",
        type=int,
        default=3,
        help="How many candidates to shortlist for deeper review",
    )
    args = parser.parse_args()

    manifest_path = args.batch / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest["source"]

    candidates: list[tuple[str, str]] = []
    labeled: list[tuple[str, str, str]] = []
    missing: list[str] = []
    for entry in _manifest_candidates(manifest):
        relative = entry["expected_output_file"]
        path = args.batch / relative
        if not path.exists():
            missing.append(relative)
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            missing.append(relative)
            continue
        candidate_id = entry["candidate_id"]
        candidates.append((candidate_id, text))
        labeled.append((candidate_id, entry["profile"], text))

    duplicate_ids = {cid for cid, _ in candidates if sum(1 for other, _ in candidates if other == cid) > 1}
    if duplicate_ids:
        raise RuntimeError(
            f"manifest contains duplicate candidate ids: {sorted(duplicate_ids)}"
        )

    if missing and not args.allow_partial:
        joined = "\n- ".join(missing)
        raise RuntimeError(
            "manual batch is incomplete; missing or empty outputs:\n- " + joined
        )
    if not candidates:
        raise RuntimeError("manual batch contains no completed candidate outputs")

    analyses = analyze_candidates(source, candidates)
    gate = assess_batch(
        analyses,
        target_words=manifest.get("target_words"),
    )
    collapse = assess_collapse(labeled)
    shortlist = rerank(
        candidates,
        analyses,
        target_words=manifest.get("target_words"),
        select=max(1, min(args.select, len(candidates))),
    )
    payload = {
        "case_id": manifest.get("case_id"),
        "candidate_count": len(candidates),
        "samples_per_profile": manifest.get("samples_per_profile", 1),
        "missing_outputs": missing,
        "gate": gate.to_dict(),
        "collapse": collapse.to_dict(),
        "rerank": shortlist.to_dict(),
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
    print(f"batch_gate={'PASS' if gate.pass_gate else 'FAIL'}")
    print(f"fidelity_evidence={gate.fidelity_evidence}")
    for failure in gate.hard_failures:
        print(f"FAIL: {failure}")
    for warning in gate.warnings:
        print(f"WARN: {warning}")

    print("--- collapse ---")
    for separation in collapse.separations:
        p_text = "n/a" if separation.p_value is None else f"{separation.p_value:.4f}"
        print(
            f"{separation.distance_mode}: "
            f"within={separation.within_profile_mean:.4f} "
            f"between={separation.between_profile_mean:.4f} "
            f"ratio={separation.separation_ratio:.3f} p={p_text}"
        )
        print(f"  {separation.interpretation}")
    for note in collapse.notes:
        print(f"NOTE: {note}")

    print("--- shortlist ---")
    for row in shortlist.ranked:
        marker = "*" if row.candidate_id in shortlist.selected else " "
        status = "" if row.eligible else " REJECTED"
        print(f"{marker} {row.candidate_id}: defects={row.defect_score:.3f}{status}")
        for reason in row.rejections:
            print(f"    reject: {reason}")
    for note in shortlist.notes:
        print(f"NOTE: {note}")

    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
