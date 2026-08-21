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
from authorship_shift.manual_batch import load_batch
from authorship_shift.rerank import rerank


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

    batch = load_batch(args.batch)

    if batch.missing and not args.allow_partial:
        joined = "\n- ".join(batch.missing)
        raise RuntimeError(
            "manual batch is incomplete; missing or empty outputs:\n- " + joined
        )
    if not batch.candidates:
        raise RuntimeError("manual batch contains no completed candidate outputs")

    analyses = analyze_candidates(batch.manifest["source"], batch.candidates)
    gate = assess_batch(analyses, target_words=batch.target_words)
    collapse = assess_collapse(batch.labeled)
    shortlist = rerank(
        batch.candidates,
        analyses,
        target_words=batch.target_words,
        select=max(1, min(args.select, len(batch.candidates))),
    )

    payload = {
        "case_id": batch.case_id,
        "candidate_count": len(batch.candidates),
        "samples_per_profile": batch.manifest.get("samples_per_profile", 1),
        "missing_outputs": batch.missing,
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

    print(f"case={batch.case_id} candidates={len(batch.candidates)}")
    for row in analyses:
        print(
            f"{row.candidate_id}: "
            f"pair_dist={row.mean_pairwise_distance:.3f} "
            f"source_3gram={row.source_trigram_overlap:.3f} "
            f"opening_repeat={row.opening_repeat_ratio:.3f} "
            f"immutables={row.immutable_coverage:.3f}"
        )
    if batch.missing:
        print(f"missing_outputs={len(batch.missing)}")
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
