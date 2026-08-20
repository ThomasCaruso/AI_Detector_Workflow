from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable
import json

from .ablation import AblationVariant, build_ablation_plan


def estimate_pipeline_calls(base_config: dict[str, Any], variant: AblationVariant) -> dict[str, Any]:
    gen = base_config.get("generation", {})
    plans_n = int(variant.plans_n if variant.plans_n is not None else gen.get("plans", 4))
    drafts_per_plan = int(gen.get("drafts_per_plan", 1))
    beam_width = int(variant.beam_width if variant.beam_width is not None else gen.get("beam_width", 4))
    beam_rounds = int(variant.beam_rounds if variant.beam_rounds is not None else gen.get("beam_rounds", 1))
    operators = list(gen.get("operators", []))
    operators_per_candidate = int(
        variant.operators_per_candidate if variant.operators_per_candidate is not None
        else gen.get("operators_per_candidate", 2)
    )

    plan_count = plans_n if variant.use_planning else 1
    drafts = plan_count * drafts_per_plan
    revisions = drafts if variant.use_global_revision else 0
    initial_candidates = drafts + revisions
    beam_upper = min(beam_width, initial_candidates)
    operator_fanout = min(operators_per_candidate, len(operators)) if variant.use_operators else 0
    operator_children = beam_rounds * beam_upper * operator_fanout
    judged_candidates = initial_candidates + operator_children

    calls = Counter()
    calls["content_lock"] = 1
    calls["structure_plan"] = 1 if variant.use_planning else 0
    calls["draft"] = drafts
    calls["global_revision"] = revisions
    calls["operator_revision"] = operator_children
    calls["fidelity_judge"] = judged_candidates
    calls["quality_judge"] = judged_candidates
    calls["selector"] = 1

    return {
        "variant": variant.name,
        "upper_bound": True,
        "plans": plan_count,
        "drafts": drafts,
        "initial_candidates": initial_candidates,
        "operator_children_upper_bound": operator_children,
        "judged_candidates_upper_bound": judged_candidates,
        "calls_by_role": dict(calls),
        "total_model_calls_upper_bound": sum(calls.values()),
    }


def estimate_ablation_suite(
    corpus_dir: str | Path,
    base_config: dict[str, Any],
    *,
    variants: str | Iterable[str] | None = None,
    split_file: str | Path | None = None,
    max_samples: int | None = None,
) -> dict[str, Any]:
    plan = build_ablation_plan(
        corpus_dir,
        variants=variants,
        split_file=split_file,
        max_samples=max_samples,
    )
    totals = Counter()
    per_variant: dict[str, dict[str, Any]] = {}
    run_counts: Counter[str] = Counter()
    for task in plan["tasks"]:
        variant = AblationVariant(**task["variant"])
        estimate = estimate_pipeline_calls(base_config, variant)
        run_counts[variant.name] += 1
        for role, count in estimate["calls_by_role"].items():
            totals[role] += count
        per_variant.setdefault(variant.name, estimate)

    variant_rows = []
    for name in sorted(per_variant):
        row = dict(per_variant[name])
        row["runs"] = run_counts[name]
        row["suite_model_calls_upper_bound"] = row["total_model_calls_upper_bound"] * run_counts[name]
        variant_rows.append(row)

    return {
        "sample_count": plan["sample_count"],
        "variant_count": plan["variant_count"],
        "run_count": plan["task_count"],
        "calls_by_role_upper_bound": dict(totals),
        "total_model_calls_upper_bound": sum(totals.values()),
        "variants": variant_rows,
        "note": (
            "This is a conservative model-call upper bound derived from pipeline topology. "
            "It does not estimate detector queries, token usage, wall-clock time, or monetary cost."
        ),
    }


def write_compute_estimate(
    corpus_dir: str | Path,
    base_config: dict[str, Any],
    output: str | Path,
    *,
    variants: str | Iterable[str] | None = None,
    split_file: str | Path | None = None,
    max_samples: int | None = None,
) -> Path:
    estimate = estimate_ablation_suite(
        corpus_dir,
        base_config,
        variants=variants,
        split_file=split_file,
        max_samples=max_samples,
    )
    path = Path(output)
    if path.suffix.lower() != ".json":
        path.mkdir(parents=True, exist_ok=True)
        json_path = path / "compute_estimate.json"
        md_path = path / "compute_estimate.md"
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        json_path = path
        md_path = path.with_suffix(".md")
    json_path.write_text(json.dumps(estimate, indent=2), encoding="utf-8")
    lines = [
        "# Local Compute Estimate",
        "",
        estimate["note"],
        "",
        f"Samples: {estimate['sample_count']}",
        f"Variants: {estimate['variant_count']}",
        f"Planned runs: {estimate['run_count']}",
        f"Model-call upper bound: **{estimate['total_model_calls_upper_bound']}**",
        "",
        "| Variant | Runs | Calls/run upper bound | Suite calls upper bound |",
        "|---|---:|---:|---:|",
    ]
    for row in estimate["variants"]:
        lines.append(
            f"| `{row['variant']}` | {row['runs']} | {row['total_model_calls_upper_bound']} | {row['suite_model_calls_upper_bound']} |"
        )
    lines += ["", "## Calls by role", ""]
    for role, count in sorted(estimate["calls_by_role_upper_bound"].items()):
        lines.append(f"- `{role}`: {count}")
    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return md_path
