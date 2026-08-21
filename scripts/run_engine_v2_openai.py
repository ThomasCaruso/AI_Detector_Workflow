from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.batch_gate import assess_batch
from authorship_shift.collapse import assess_collapse
from authorship_shift.engine_v2 import GenerationControls, GenerationProfile, generate_candidate_batch
from authorship_shift.generation_profiles import default_generation_profiles
from authorship_shift.rerank import rerank
from authorship_shift.providers.openai_responses import OpenAIResponsesGenerator


def _load_case(path: Path, case_id: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for case in payload.get("cases", []):
        if case.get("id") == case_id:
            return case
    raise KeyError(f"case {case_id!r} not found in {path}")


def _profiles_for_case(case: dict) -> list[GenerationProfile]:
    task = str(case.get("task", "")).strip()
    target_words = case.get("target_words")
    suffix = f"\n\nAssignment: {task}"
    if target_words:
        suffix += f"\nTarget length: approximately {int(target_words)} words."

    profiles = []
    for profile in default_generation_profiles():
        controls = GenerationControls(
            temperature=profile.controls.temperature,
            top_p=profile.controls.top_p,
            seed=profile.controls.seed,
            max_tokens=max(256, int(target_words * 2.2)) if target_words else 1024,
        )
        profiles.append(
            replace(
                profile,
                directive=profile.directive + suffix,
                controls=controls,
            )
        )
    return profiles


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run an AuthorshipShift Engine v2 candidate batch through the OpenAI Responses API."
    )
    parser.add_argument("case_id")
    parser.add_argument("--model", required=True, help="OpenAI API model name")
    parser.add_argument(
        "--case-file",
        type=Path,
        default=ROOT / "evals" / "engine_v2_seed_cases.json",
    )
    parser.add_argument("--candidates-per-profile", type=int, default=2)
    parser.add_argument(
        "--allow-sampling-controls",
        action="store_true",
        help="Send temperature/top_p. Use only if the selected model supports them.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually make API requests. Without this flag the command is a zero-cost dry run.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON path. Defaults to experiments/engine_v2_openai/<case>-<model>.json",
    )
    args = parser.parse_args()

    if args.candidates_per_profile < 1:
        raise ValueError("--candidates-per-profile must be >= 1")

    case = _load_case(args.case_file, args.case_id)
    profiles = _profiles_for_case(case)
    call_count = len(profiles) * args.candidates_per_profile

    print(f"case={args.case_id}")
    print(f"model={args.model}")
    print(f"profiles={len(profiles)} candidates_per_profile={args.candidates_per_profile}")
    print(f"planned_api_calls={call_count}")

    if not args.execute:
        print("DRY RUN: no API requests were made. Add --execute only when you intend to incur API usage.")
        return 0

    generator = OpenAIResponsesGenerator(
        args.model,
        allow_sampling_controls=args.allow_sampling_controls,
    )
    atoms = [str(item) for item in case.get("required_qualifications", [])]
    if not atoms:
        atoms = [str(case.get("task", "preserve the supplied content"))]

    run = generate_candidate_batch(
        source=str(case["source"]),
        content_atoms=atoms,
        generator=generator,
        profiles=profiles,
        candidates_per_profile=args.candidates_per_profile,
    )
    analyses = [candidate.analysis for candidate in run.candidates if candidate.analysis]
    gate = assess_batch(analyses, target_words=case.get("target_words"))
    collapse = assess_collapse(
        [(c.id, c.profile, c.text) for c in run.candidates]
    )
    shortlist = rerank(
        [(c.id, c.text) for c in run.candidates],
        analyses,
        target_words=case.get("target_words"),
        select=max(1, min(3, len(run.candidates))),
    )

    output = args.output
    if output is None:
        safe_model = args.model.replace("/", "-").replace(":", "-")
        output = ROOT / "experiments" / "engine_v2_openai" / f"{args.case_id}-{safe_model}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = run.to_dict()
    payload["case_id"] = args.case_id
    payload["model"] = args.model
    payload["batch_gate"] = gate.to_dict()
    payload["collapse"] = collapse.to_dict()
    payload["rerank"] = shortlist.to_dict()
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"batch_gate_pass={gate.pass_gate}")
    print(f"mean_pairwise_distance={gate.mean_pairwise_distance:.3f}")
    print(f"fidelity_evidence={gate.fidelity_evidence}")
    if gate.hard_failures:
        print("hard_failures:")
        for failure in gate.hard_failures:
            print(f"- {failure}")
    for separation in collapse.separations:
        p_text = "n/a" if separation.p_value is None else f"{separation.p_value:.4f}"
        print(
            f"collapse[{separation.distance_mode}]: "
            f"ratio={separation.separation_ratio:.3f} p={p_text} "
            f"-> {separation.interpretation}"
        )
    for note in collapse.notes:
        print(f"NOTE: {note}")
    print(f"shortlist={shortlist.selected}")
    print(output)
    return 0 if gate.pass_gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
