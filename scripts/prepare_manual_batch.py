from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.generation_profiles import default_generation_profiles


def _load_case(path: Path, case_id: str) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for case in payload.get("cases", []):
        if case.get("id") == case_id:
            return case
    available = ", ".join(case.get("id", "?") for case in payload.get("cases", []))
    raise ValueError(f"case {case_id!r} not found; available: {available}")


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
    args = parser.parse_args()

    case = _load_case(args.corpus, args.case_id)
    out = args.out or (ROOT / "experiments" / "manual_batches" / args.case_id)
    prompts_dir = out / "prompts"
    outputs_dir = out / "outputs"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    profiles = default_generation_profiles(base_seed=args.base_seed)
    manifest = {
        "case_id": args.case_id,
        "genre": case.get("genre"),
        "target_words": case.get("target_words"),
        "source": case["source"],
        "task": case["task"],
        "required_qualifications": case.get("required_qualifications", []),
        "profiles": [],
    }

    for index, profile in enumerate(profiles, start=1):
        filename = f"{index:02d}_{profile.name}.md"
        (prompts_dir / filename).write_text(
            _render_prompt(case, profile.name, profile.directive),
            encoding="utf-8",
        )
        manifest["profiles"].append(
            {
                "index": index,
                "name": profile.name,
                "prompt_file": f"prompts/{filename}",
                "expected_output_file": f"outputs/{index:02d}_{profile.name}.txt",
                "requested_controls": profile.controls.to_dict(),
            }
        )

    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out / "README.md").write_text(
        "# Manual candidate batch\n\n"
        "Run each file in `prompts/` as a separate model generation. Save only the resulting prose "
        "to the matching path under `outputs/`. Do not combine several profiles into one model response; "
        "the purpose is to preserve independent generation trajectories where the model surface allows it.\n",
        encoding="utf-8",
    )

    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
