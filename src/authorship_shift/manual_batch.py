"""Preparation and loading of zero-API manual candidate batches.

This lives in the package rather than in a script so the cross-domain collapse
suite can prepare and read batches directly instead of shelling out to the CLI.
`scripts/prepare_manual_batch.py` and `scripts/analyze_manual_batch.py` are thin
wrappers over these functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, Sequence

from .engine_v2 import GenerationControls, GenerationProfile
from .generation_profiles import default_generation_profiles

MANIFEST_SCHEMA_VERSION = 2

# Below this, within-profile dispersion cannot be measured at all.
MIN_SAMPLES_FOR_COLLAPSE = 2


def load_case(path: str | Path, case_id: str) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    for case in payload.get("cases", []):
        if case.get("id") == case_id:
            return case
    available = ", ".join(case.get("id", "?") for case in payload.get("cases", []))
    raise ValueError(f"case {case_id!r} not found; available: {available}")


def load_all_cases(path: str | Path) -> list[dict]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases", [])
    if not cases:
        raise ValueError(f"no cases found in {path}")
    return list(cases)


def sample_controls(controls: GenerationControls, sample_index: int) -> GenerationControls:
    """Mirror the seed offset that generate_candidate_batch applies to replicates."""

    if controls.seed is None or sample_index == 0:
        return controls
    return GenerationControls(
        temperature=controls.temperature,
        top_p=controls.top_p,
        seed=controls.seed + sample_index,
        max_tokens=controls.max_tokens,
    )


def render_prompt(case: dict, profile_name: str, directive: str) -> str:
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


def _readme_text(samples: int) -> str:
    replicate_note = (
        "\nThis batch requests "
        f"{samples} independent samples per profile. Replicates are what make "
        "within-profile dispersion measurable, so profile effects can be told apart "
        "from ordinary sampling noise. Run every prompt separately even when two "
        "prompts for the same profile are identical; that identity is the point.\n"
        if samples >= MIN_SAMPLES_FOR_COLLAPSE
        else
        "\nThis batch requests one sample per profile, so within-profile dispersion "
        "cannot be measured and profile effects cannot be separated from sampling "
        "noise. Use `--samples-per-profile 2` or more for that experiment.\n"
    )
    return (
        "# Manual candidate batch\n\n"
        "Run each file in `prompts/` as a separate model generation. Save only the resulting prose "
        "to the matching path under `outputs/`. Do not combine several profiles into one model response; "
        "the purpose is to preserve independent generation trajectories where the model surface allows it.\n"
        + replicate_note
    )


def prepare_batch(
    case: dict,
    out: str | Path,
    *,
    samples_per_profile: int = 1,
    profiles: Sequence[GenerationProfile] | None = None,
    base_seed: int = 100,
) -> dict:
    """Write prompts, an outputs directory, a manifest, and a README.

    Returns the manifest. A single sample per profile keeps the original
    filenames so batches and docs written against the v1 layout stay valid.
    """

    if samples_per_profile < 1:
        raise ValueError("samples_per_profile must be >= 1")

    root = Path(out)
    prompts_dir = root / "prompts"
    outputs_dir = root / "outputs"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    profile_list = list(profiles) if profiles else default_generation_profiles(base_seed=base_seed)
    manifest: dict[str, Any] = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "case_id": case.get("id"),
        "genre": case.get("genre"),
        "target_words": case.get("target_words"),
        "samples_per_profile": samples_per_profile,
        "source": case["source"],
        "task": case["task"],
        "required_qualifications": case.get("required_qualifications", []),
        "candidates": [],
        "profiles": [],
    }

    for index, profile in enumerate(profile_list, start=1):
        profile_entry: dict[str, Any] = {
            "index": index,
            "name": profile.name,
            "requested_controls": profile.controls.to_dict(),
            "candidate_ids": [],
        }

        for sample_index in range(samples_per_profile):
            stem = f"{index:02d}_{profile.name}"
            if samples_per_profile > 1:
                stem = f"{stem}_c{sample_index + 1}"
            candidate_id = f"p{index}-c{sample_index + 1}"

            (prompts_dir / f"{stem}.md").write_text(
                render_prompt(case, profile.name, profile.directive),
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
                    "requested_controls": sample_controls(
                        profile.controls, sample_index
                    ).to_dict(),
                }
            )
            profile_entry["candidate_ids"].append(candidate_id)

        # Retained so readers written against the v1 manifest keep working.
        first = manifest["candidates"][-samples_per_profile]
        profile_entry["prompt_file"] = first["prompt_file"]
        profile_entry["expected_output_file"] = first["expected_output_file"]
        manifest["profiles"].append(profile_entry)

    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (root / "README.md").write_text(_readme_text(samples_per_profile), encoding="utf-8")
    return manifest


def manifest_candidates(manifest: dict) -> list[dict]:
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


@dataclass
class LoadedBatch:
    batch_dir: Path
    manifest: dict
    candidates: list[tuple[str, str]] = field(default_factory=list)
    labeled: list[tuple[str, str, str]] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def case_id(self) -> str:
        return str(self.manifest.get("case_id", self.batch_dir.name))

    @property
    def genre(self) -> str | None:
        return self.manifest.get("genre")

    @property
    def target_words(self) -> int | None:
        return self.manifest.get("target_words")

    @property
    def expected_count(self) -> int:
        return len(manifest_candidates(self.manifest))

    @property
    def complete(self) -> bool:
        return not self.missing and bool(self.candidates)


def load_batch(batch_dir: str | Path) -> LoadedBatch:
    """Read a prepared batch and whatever outputs exist so far."""

    root = Path(batch_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"no manifest.json in {root}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    candidates: list[tuple[str, str]] = []
    labeled: list[tuple[str, str, str]] = []
    missing: list[str] = []
    seen: set[str] = set()

    for entry in manifest_candidates(manifest):
        candidate_id = entry["candidate_id"]
        if candidate_id in seen:
            raise ValueError(f"manifest contains duplicate candidate id {candidate_id!r}")
        seen.add(candidate_id)

        relative = entry["expected_output_file"]
        path = root / relative
        if not path.exists():
            missing.append(relative)
            continue
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            missing.append(relative)
            continue
        candidates.append((candidate_id, text))
        labeled.append((candidate_id, entry["profile"], text))

    return LoadedBatch(
        batch_dir=root,
        manifest=manifest,
        candidates=candidates,
        labeled=labeled,
        missing=missing,
    )
