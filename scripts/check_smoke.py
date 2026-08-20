from __future__ import annotations

import argparse

from authorship_shift.smoke import analyze_smoke_suite, write_smoke_report


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate AuthorshipShift smoke-suite health after local generation.")
    parser.add_argument("--suite", default="ablations/smoke_v08")
    parser.add_argument("--config", default="configs/smoke.json")
    parser.add_argument("--mode", choices=["checkpoint", "full"], default="checkpoint")
    parser.add_argument("--output")
    args = parser.parse_args()

    report_path = write_smoke_report(args.suite, args.config, mode=args.mode, output=args.output)
    report = analyze_smoke_suite(args.suite, args.config, mode=args.mode)
    print(report_path)
    print(f"Smoke diagnostic: {'PASS' if report['ok'] else 'FAIL'}")
    print(f"Completed runs: {report['completed_runs']} / {report['expected_planned_runs']}")
    print(f"Target calls: {report['target_measured_model_calls']} / {report['target_expected_model_calls']}")
    print(f"Errors: {len(report['errors'])}; warnings: {len(report['warnings'])}")
    for error in report["errors"]:
        print(f"ERROR: {error}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
