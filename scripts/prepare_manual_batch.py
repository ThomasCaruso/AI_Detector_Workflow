from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.engine_v2 import GenerationControls
from authorship_shift.generation_profiles import default_generation_profiles

MANIFEST_SCHEMA_VERSION = 2


def _load_case(path: Path, case_id: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for case in payload.get("cases", []):
        if case.get("id") == case_id:
            return case
    available = ", ".join(case.get("id", "?") for case in payload.get("cases", []))
    raise ValueError(f"case {case_id!r} not found; available: {available}")


def _sample_controls(controls: GenerationControls, sample_index: int) -> GenerationControls:
    """Mirror the seed offset that generate_candidate_batch applies to replicates."""

    if controls.seed is None or sample_index == 0:
        return controls
    return GenerationControls(
        temperature=controls.temperature,
        top_p=controls.top_p,
        seed=controls.seed + sample_index,
        max_tokens=controls.max_tokens,
    )


def _render_prompt(case: dict, profile_name: str, directive: str) -> str:
    qualifications = case.get("required_qualifications", [])
    qualification_text = "\n".join(f"- {item}" for item in qualifications) or "- none"
    target_words = case.get("target_words")
    length_line = (
        f"Aim for approximately {target_words} words unless the task itself requires another length."
        if target_words
        else "Use the length required by the task."
    )

    return f"""# AuthorshipShift Engine v2 manual candidate

## Task

{case['task']}

## Source / locked facts

{case['source']}

## Required qualifications

{qualification_text}

## Generation profile: {profile_name}

{directive}

## Output requirements

- Preserve every supplied fact, number, causal relationship, and qualification.
- Do not invent evidence, quotations, experience, or additional factual claims.
- {length_line}
- Return only the finished prose; do not discuss the generation profile or these instructions.
"""


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

    case = _load_case(args.corpus, args.case_id)
    out = args.out or (ROOT / "experiments" / "manual_batches" / args.case_id)
    prompts_dir = out / "prompts"
    outputs_dir = out / "outputs"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    profiles = default_generation_profiles(base_seed=args.base_seed)
    samples = args.samples_per_profile
    manifest = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "case_id": args.case_id,
        "genre": case.get("genre"),
        "target_words": case.get("target_words"),
        "samples_per_profile": samples,
        "source": case["source"],
        "task": case["task"],
        "required_qualifications": case.get("required_qualifications", []),
        "candidates": [],
        "profiles": [],
    }

    for index, profile in enumerate(profiles, start=1):
        profile_entry = {
            "index": index,
            "name": profile.name,
            "requested_controls": profile.controls.to_dict(),
            "candidate_ids": [],
        }

        for sample_index in range(samples):
            # A single sample per profile keeps the original filenames, so batches
            # and docs written against the v1 layout stay valid.
            stem = f"{index:02d}_{profile.name}"
            if samples > 1:
                stem = f"{stem}_c{sample_index + 1}"
            candidate_id = f"p{index}-c{sample_index + 1}"

            (prompts_dir / f"{stem}.md").write_text(
                _render_prompt(case, profile.name, profile.directive),
                encoding="utf-8",
            )
            manifest["candidates"].append(
                {
                    "candidate_id": candidate_id,
                    "profile": profile.name,
                    "profile_index": index,
                    "sample_index": sample_index + 1,
                    "prompt_file": f"prompts/{stem}.md",
                    "expected_output_file": f"outputs/{stem}.txt",
                    "requested_controls": _sample_controls(
                        profile.controls, sample_index
                    ).to_dict(),
                }
            )
            profile_entry["candidate_ids"].append(candidate_id)

        # Retained so readers written against the v1 manifest keep working.
        first = manifest["candidates"][-samples]
        profile_entry["prompt_file"] = first["prompt_file"]
        profile_entry["expected_output_file"] = first["expected_output_file"]
        manifest["profiles"].append(profile_entry)

    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    replicate_note = (
        "\nThis batch requests "
        f"{samples} independent samples per profile. Replicates are what make "
        "within-profile dispersion measurable, so profile effects can be told apart "
        "from ordinary sampling noise. Run every prompt separately even when two "
        "prompts for the same profile are identical; that identity is the point.\n"
        if samples > 1
        else
        "\nThis batch requests one sample per profile, so within-profile dispersion "
        "cannot be measured and profile effects cannot be separated from sampling "
        "noise. Use `--samples-per-profile 2` or more for that experiment.\n"
    )
    (out / "README.md").write_text(
        "# Manual candidate batch\n\n"
        "Run each file in `prompts/` as a separate model generation. Save only the resulting prose "
        "to the matching path under `outputs/`. Do not combine several profiles into one model response; "
        "the purpose is to preserve independent generation trajectories where the model surface allows it.\n"
        + replicate_note,
        encoding="utf-8",
    )

    print(out)
    print(f"profiles={len(profiles)} samples_per_profile={samples} prompts={len(manifest['candidates'])}")
    if samples < 2:
        print(
            "note: within-profile dispersion is unmeasurable with one sample per profile; "
            "use --samples-per-profile 2 or more to test for distribution collapse"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
