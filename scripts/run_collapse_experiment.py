"""Orchestrate the cross-domain collapse experiment.

    5 domains x 5 generation profiles x 2 independent samples = 50 generations

Three subcommands:

    prepare   write every domain's prompt set
    status    show which generations are still outstanding
    report    aggregate the completed batches into one table and one verdict

No API calls are made by any subcommand. Generation happens in whatever model
surface you are testing; this tool only prepares prompts and analyzes outputs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.collapse_suite import run_suite
from authorship_shift.manual_batch import (
    MIN_SAMPLES_FOR_COLLAPSE,
    load_all_cases,
    load_batch,
    prepare_batch,
)
from authorship_shift.verdict_guard import apply_final_verdict_guard

DEFAULT_CASES = ROOT / "evals" / "engine_v2_seed_cases.json"
DEFAULT_ROOT = ROOT / "experiments" / "collapse_suite"


def _batch_dirs(root: Path, cases: Path | None = None) -> list[Path]:
    if not root.exists():
        raise SystemExit(
            f"no prepared batches under {root}. Run the 'prepare' subcommand first."
        )
    dirs = [path for path in root.iterdir() if (path / "manifest.json").exists()]
    if not dirs:
        raise SystemExit(
            f"no prepared batches under {root}. Run the 'prepare' subcommand first."
        )

    # Report domains in seed-case order rather than directory-alphabetical order,
    # so the table reads the same way every run and matches the corpus.
    order: dict[str, int] = {}
    if cases and cases.exists():
        order = {
            str(case.get("id")): index
            for index, case in enumerate(load_all_cases(cases))
        }
    return sorted(dirs, key=lambda path: (order.get(path.name, len(order)), path.name))


def cmd_prepare(args: argparse.Namespace) -> int:
    if args.samples_per_profile < MIN_SAMPLES_FOR_COLLAPSE:
        raise SystemExit(
            f"--samples-per-profile must be at least {MIN_SAMPLES_FOR_COLLAPSE}: "
            "with one sample per profile there is no within-profile dispersion and "
            "the collapse experiment cannot be run"
        )

    cases = load_all_cases(args.cases)
    args.root.mkdir(parents=True, exist_ok=True)

    total = 0
    for case in cases:
        out = args.root / str(case["id"])
        manifest = prepare_batch(
            case,
            out,
            samples_per_profile=args.samples_per_profile,
            base_seed=args.base_seed,
        )
        count = len(manifest["candidates"])
        total += count
        print(f"{case['id']:28} genre={case.get('genre', '?'):24} prompts={count}")

    print()
    print(f"root={args.root}")
    print(
        f"domains={len(cases)} profiles=5 samples_per_profile={args.samples_per_profile} "
        f"total_generations={total}"
    )
    print(
        "Run every prompt as a separate generation. Two prompts for the same profile "
        "are identical by design; the difference between their outputs is the "
        "within-profile term."
    )
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    outstanding = 0
    for path in _batch_dirs(args.root, args.cases):
        batch = load_batch(path)
        done = len(batch.candidates)
        expected = batch.expected_count
        outstanding += len(batch.missing)
        marker = "ok " if batch.complete else "   "
        print(f"{marker} {batch.case_id:28} {done}/{expected}")
        if args.verbose:
            for relative in batch.missing:
                print(f"      missing: {relative}")
    print()
    print(f"outstanding_generations={outstanding}")
    return 0 if outstanding == 0 else 1


def cmd_report(args: argparse.Namespace) -> int:
    report = run_suite(
        _batch_dirs(args.root, args.cases),
        permutations=args.permutations,
        seed=args.seed,
        select=args.select,
    )
    # Partial reports remain useful for diagnostics, but only a complete suite
    # with enough checked, gate-passing domains may issue a training-direction
    # verdict. This prevents a one-domain pilot from accidentally recommending
    # LoRA while four domains are still unmeasured.
    report = apply_final_verdict_guard(report)

    markdown = report.to_markdown()
    print(markdown)

    md_path = args.markdown or (args.root / "COLLAPSE_REPORT.md")
    json_path = args.json_out or (args.root / "collapse_report.json")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding="utf-8")
    json_path.write_text(
        json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\nwrote {md_path}")
    print(f"wrote {json_path}")

    if report.measured_count == 0:
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Directory holding one prepared batch per domain",
    )
    parser.add_argument(
        "--cases",
        type=Path,
        default=DEFAULT_CASES,
        help="Seed-case file; also fixes the domain order used in reports",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare", help="Write every domain's prompt set")
    prepare.add_argument("--samples-per-profile", type=int, default=2)
    prepare.add_argument("--base-seed", type=int, default=100)
    prepare.set_defaults(func=cmd_prepare)

    status = sub.add_parser("status", help="Show outstanding generations")
    status.add_argument("--verbose", action="store_true")
    status.set_defaults(func=cmd_status)

    report = sub.add_parser("report", help="Aggregate completed batches")
    report.add_argument("--permutations", type=int, default=2000)
    report.add_argument("--seed", type=int, default=12345)
    report.add_argument("--select", type=int, default=3)
    report.add_argument("--markdown", type=Path, default=None)
    report.add_argument("--json-out", type=Path, default=None)
    report.set_defaults(func=cmd_report)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
