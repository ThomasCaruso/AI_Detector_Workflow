from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.manual_batch import MIN_SAMPLES_FOR_COLLAPSE, load_case, prepare_batch


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prepare a zero-API manual candidate batch for ChatGPT, Codex, or another model surface."
    )
    parser.add_argument("case_id", help="Case id from evals/engine_v2_seed_cases.json")
    parser.add_argument(
        "--corpus",
        type=Path,
        default=ROOT / "evals" / "engine_v2_seed_cases.json",
        help="Path to the Engine v2 seed-cases JSON file",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory; defaults to experiments/manual_batches/<case_id>",
    )
    parser.add_argument("--base-seed", type=int, default=100)
    parser.add_argument(
        "--samples-per-profile",
        type=int,
        default=1,
        help=(
            "Independent generations to request per profile. Use 2 or more to make "
            "within-profile dispersion measurable, which is required before profile "
            "effects can be separated from ordinary sampling noise."
        ),
    )
    args = parser.parse_args()

    if args.samples_per_profile < 1:
        raise SystemExit("--samples-per-profile must be >= 1")

    case = load_case(args.corpus, args.case_id)
    out = args.out or (ROOT / "experiments" / "manual_batches" / args.case_id)
    manifest = prepare_batch(
        case,
        out,
        samples_per_profile=args.samples_per_profile,
        base_seed=args.base_seed,
    )

    print(out)
    print(
        f"profiles={len(manifest['profiles'])} "
        f"samples_per_profile={args.samples_per_profile} "
        f"prompts={len(manifest['candidates'])}"
    )
    if args.samples_per_profile < MIN_SAMPLES_FOR_COLLAPSE:
        print(
            "note: within-profile dispersion is unmeasurable with one sample per profile; "
            "use --samples-per-profile 2 or more to test for distribution collapse"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
