from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from .ablation import variant_registry
from .compute import estimate_pipeline_calls


REQUIRED_RUN_ARTIFACTS = (
    "manifest.json",
    "config.json",
    "source.txt",
    "content_lock.json",
    "plans.json",
    "ranking.json",
    "selection.json",
    "pipeline_stats.json",
    "ablation_summary.json",
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _resolve_run_root(suite_root: Path, row: dict[str, Any]) -> Path:
    """Resolve a run directory without trusting machine-specific stored paths.

    New and legacy suite summaries may contain absolute experiment_root values. The
    canonical on-disk suite layout is stable, so prefer an existing declared path but
    fall back to runs/<sample_id>/<variant> when a suite has been moved.
    """
    declared = str(row.get("experiment_root", ""))
    if declared:
        raw = Path(declared)
        candidate = raw if raw.is_absolute() else suite_root / raw
        if candidate.exists():
            return candidate.resolve()
    return (suite_root / "runs" / str(row.get("sample_id", "")) / str(row.get("variant", ""))).resolve()


def _expected_variants(config: dict[str, Any]) -> list[str]:
    variants = [str(v) for v in config.get("ablation", {}).get("default_variants", []) if str(v)]
    if not variants:
        raise ValueError("Smoke config has no ablation.default_variants")
    return variants


def _expected_calls(config: dict[str, Any], variants: list[str]) -> dict[str, int]:
    registry = variant_registry()
    missing = [name for name in variants if name not in registry]
    if missing:
        raise ValueError("Unknown smoke variants: " + ", ".join(missing))
    return {
        name: int(estimate_pipeline_calls(config, registry[name])["total_model_calls_upper_bound"])
        for name in variants
    }


def _task_key(task: dict[str, Any]) -> tuple[str, str]:
    variant = task.get("variant", {}) or {}
    return str(task.get("sample_id", "")), str(variant.get("name", ""))


def _row_key(row: dict[str, Any]) -> tuple[str, str]:
    return str(row.get("sample_id", "")), str(row.get("variant", ""))


def analyze_smoke_suite(
    suite_dir: str | Path,
    config_path: str | Path,
    *,
    mode: str = "checkpoint",
) -> dict[str, Any]:
    """Validate structural health of the checked-in smoke experiment.

    checkpoint mode requires the first paired three-variant batch. full mode requires
    the complete planned matrix. Research outcomes such as low gate survival are
    warnings; reproducibility, accounting, artifact, and zero-detector violations are
    hard errors.
    """
    if mode not in {"checkpoint", "full"}:
        raise ValueError("mode must be 'checkpoint' or 'full'")

    root = Path(suite_dir).resolve()
    config_file = Path(config_path).resolve()
    errors: list[str] = []
    warnings: list[str] = []
    run_diagnostics: list[dict[str, Any]] = []

    plan_path = root / "suite_plan.json"
    results_path = root / "suite_results.json"
    if not plan_path.exists():
        return {"ok": False, "mode": mode, "errors": [f"missing suite plan: {plan_path}"], "warnings": [], "runs": []}
    if not results_path.exists():
        return {"ok": False, "mode": mode, "errors": [f"missing suite results: {results_path}"], "warnings": [], "runs": []}
    if not config_file.exists():
        return {"ok": False, "mode": mode, "errors": [f"missing smoke config: {config_file}"], "warnings": [], "runs": []}

    plan = _read_json(plan_path)
    payload = _read_json(results_path)
    config = _read_json(config_file)
    variants = _expected_variants(config)
    expected_calls = _expected_calls(config, variants)
    tasks = list(plan.get("tasks", []))
    runs = list(payload.get("runs", []))

    expected_samples = int(config.get("ablation", {}).get("max_development_samples", 0) or 0)
    expected_task_count = expected_samples * len(variants)
    if int(plan.get("sample_count", 0) or 0) != expected_samples:
        errors.append(f"plan sample count drifted: expected {expected_samples}, found {plan.get('sample_count')}")
    if int(plan.get("variant_count", 0) or 0) != len(variants):
        errors.append(f"plan variant count drifted: expected {len(variants)}, found {plan.get('variant_count')}")
    if int(plan.get("task_count", 0) or 0) != expected_task_count or len(tasks) != expected_task_count:
        errors.append(f"plan task count drifted: expected {expected_task_count}, found {plan.get('task_count')} / {len(tasks)} tasks")

    plan_variant_names = [str(row.get("name", "")) for row in plan.get("variants", [])]
    if plan_variant_names != variants:
        errors.append(f"plan variants differ from smoke config: expected {variants}, found {plan_variant_names}")

    first_tasks = tasks[: len(variants)]
    if len(first_tasks) != len(variants):
        errors.append("plan does not contain a complete first paired batch")
        checkpoint_sample = ""
    else:
        checkpoint_sample = str(first_tasks[0].get("sample_id", ""))
        first_names = [str((task.get("variant") or {}).get("name", "")) for task in first_tasks]
        first_samples = {str(task.get("sample_id", "")) for task in first_tasks}
        if first_names != variants:
            errors.append(f"first batch variant order drifted: expected {variants}, found {first_names}")
        if len(first_samples) != 1 or not checkpoint_sample:
            errors.append("first smoke batch is not paired on exactly one source sample")

    row_index: dict[tuple[str, str], dict[str, Any]] = {}
    duplicates: list[tuple[str, str]] = []
    for row in runs:
        key = _row_key(row)
        if key in row_index:
            duplicates.append(key)
        row_index[key] = row
    if duplicates:
        errors.append("duplicate run records: " + ", ".join(f"{sample}/{variant}" for sample, variant in duplicates))

    target_keys = [_task_key(task) for task in (first_tasks if mode == "checkpoint" else tasks)]
    missing_targets = [key for key in target_keys if key not in row_index]
    if missing_targets:
        errors.append("missing required smoke runs: " + ", ".join(f"{sample}/{variant}" for sample, variant in missing_targets))

    if mode == "checkpoint" and len(runs) > len(variants):
        warnings.append(f"checkpoint contains {len(runs)} completed runs; only the first paired {len(variants)} are required")
    if mode == "full" and len(runs) != expected_task_count:
        errors.append(f"full smoke suite requires exactly {expected_task_count} run records; found {len(runs)}")

    declared_completed = int(payload.get("completed_runs", len(runs)) or 0)
    if declared_completed != len(runs):
        errors.append(f"suite completed_runs mismatch: field={declared_completed}, records={len(runs)}")
    if int(payload.get("planned_runs", expected_task_count) or 0) != expected_task_count:
        errors.append(f"suite planned_runs mismatch: expected {expected_task_count}, found {payload.get('planned_runs')}")

    external_cfg = config.get("external_evaluation", {}) or {}
    if int(external_cfg.get("development_queries_allowed", 0) or 0) != 0:
        errors.append("smoke config development detector budget is not zero")
    if int(external_cfg.get("milestone_queries_budget", 0) or 0) != 0:
        errors.append("smoke config milestone detector budget is not zero")

    completed_model_calls = 0
    target_model_calls = 0
    for key in target_keys:
        target_model_calls += expected_calls.get(key[1], 0)

    for row in runs:
        sample_id, variant = _row_key(row)
        run_errors: list[str] = []
        run_warnings: list[str] = []
        if variant not in expected_calls:
            run_errors.append(f"unexpected variant: {variant}")
            expected = None
        else:
            expected = expected_calls[variant]

        measured_calls = int(row.get("total_model_calls", 0) or 0)
        completed_model_calls += measured_calls
        call_counts = dict(row.get("call_counts", {}) or {})
        if expected is not None and measured_calls != expected:
            run_errors.append(f"model-call drift: expected {expected}, measured {measured_calls}")
        if sum(int(v or 0) for v in call_counts.values()) != measured_calls:
            run_errors.append("call_counts do not sum to total_model_calls")
        if int(row.get("external_queries_used", 0) or 0) != 0:
            run_errors.append("external detector query usage is nonzero")
        if int(row.get("candidate_count", 0) or 0) < 1:
            run_errors.append("candidate_count is zero")
        if int(row.get("beam_size", 0) or 0) < 1:
            run_errors.append("final beam is empty")
        if not list(row.get("models", []) or []):
            run_warnings.append("no model identities were summarized")
        if float(row.get("hard_gate_pass_rate", 0.0) or 0.0) <= 0.0:
            run_warnings.append("no candidates survived all hard gates")
        if float(row.get("mean_fidelity", 0.0) or 0.0) <= 0.0:
            run_warnings.append("mean fidelity is zero")

        run_root = _resolve_run_root(root, row)
        missing_artifacts = [name for name in REQUIRED_RUN_ARTIFACTS if not (run_root / name).exists()]
        if missing_artifacts:
            run_errors.append("missing artifacts: " + ", ".join(missing_artifacts))
        else:
            stats = _read_json(run_root / "pipeline_stats.json")
            if int(stats.get("total_model_calls", 0) or 0) != measured_calls:
                run_errors.append("pipeline_stats total_model_calls differs from suite summary")
            if dict(stats.get("call_counts", {}) or {}) != call_counts:
                run_errors.append("pipeline_stats call_counts differ from suite summary")
            run_config = _read_json(run_root / "config.json")
            run_external = run_config.get("external_evaluation", {}) or {}
            if int(run_external.get("development_queries_allowed", 0) or 0) != 0 or int(run_external.get("milestone_queries_budget", 0) or 0) != 0:
                run_errors.append("child run external detector budget is not forced to zero")
            ranking = _read_json(run_root / "ranking.json")
            if not isinstance(ranking, list) or not ranking:
                run_errors.append("ranking.json is empty or malformed")
            else:
                for index, ranked in enumerate(ranking):
                    if not isinstance(ranked.get("fidelity"), dict) or not isinstance(ranked.get("quality"), dict):
                        run_errors.append(f"ranking row {index} lacks parsed fidelity/quality objects")
                        break

        errors.extend(f"{sample_id}/{variant}: {message}" for message in run_errors)
        warnings.extend(f"{sample_id}/{variant}: {message}" for message in run_warnings)
        run_diagnostics.append({
            "sample_id": sample_id,
            "variant": variant,
            "run_root": str(run_root),
            "expected_model_calls": expected,
            "measured_model_calls": measured_calls,
            "hard_gate_pass_rate": float(row.get("hard_gate_pass_rate", 0.0) or 0.0),
            "mean_fidelity": float(row.get("mean_fidelity", 0.0) or 0.0),
            "mean_quality_delta": float(row.get("mean_quality_delta", 0.0) or 0.0),
            "errors": run_errors,
            "warnings": run_warnings,
        })

    if target_keys and all(key in row_index for key in target_keys):
        measured_target_calls = sum(int(row_index[key].get("total_model_calls", 0) or 0) for key in target_keys)
        if measured_target_calls != target_model_calls:
            errors.append(f"target batch call total drifted: expected {target_model_calls}, measured {measured_target_calls}")
    else:
        measured_target_calls = None

    return {
        "ok": not errors,
        "mode": mode,
        "suite": str(root),
        "config": str(config_file),
        "expected_variants": variants,
        "expected_calls_per_variant": expected_calls,
        "expected_samples": expected_samples,
        "expected_planned_runs": expected_task_count,
        "completed_runs": len(runs),
        "checkpoint_sample": checkpoint_sample,
        "target_expected_model_calls": target_model_calls,
        "target_measured_model_calls": measured_target_calls,
        "completed_model_calls": completed_model_calls,
        "errors": errors,
        "warnings": warnings,
        "runs": run_diagnostics,
    }


def build_smoke_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Smoke Diagnostic Report",
        "",
        f"Status: **{'PASS' if report.get('ok') else 'FAIL'}**",
        f"Mode: `{report.get('mode', '')}`",
        f"Completed runs: **{report.get('completed_runs', 0)} / {report.get('expected_planned_runs', 0)}**",
        f"Target model calls: **{report.get('target_measured_model_calls')} / {report.get('target_expected_model_calls')}**",
        "",
    ]
    errors = list(report.get("errors", []))
    warnings = list(report.get("warnings", []))
    lines += ["## Errors", ""]
    lines += [f"- {error}" for error in errors] or ["- None."]
    lines += ["", "## Warnings", ""]
    lines += [f"- {warning}" for warning in warnings] or ["- None."]
    lines += ["", "## Runs", "", "| Sample | Variant | Calls | Gate pass | Fidelity | Quality Δ |", "|---|---|---:|---:|---:|---:|"]
    for row in report.get("runs", []):
        lines.append(
            f"| `{row['sample_id']}` | `{row['variant']}` | {row['measured_model_calls']} / {row['expected_model_calls']} | "
            f"{row['hard_gate_pass_rate']:.3f} | {row['mean_fidelity']:.3f} | {row['mean_quality_delta']:+.3f} |"
        )
    return "\n".join(lines).rstrip() + "\n"


def write_smoke_report(
    suite_dir: str | Path,
    config_path: str | Path,
    *,
    mode: str = "checkpoint",
    output: str | Path | None = None,
) -> Path:
    root = Path(suite_dir).resolve()
    report = analyze_smoke_suite(root, config_path, mode=mode)
    md_path = Path(output).resolve() if output else root / "smoke_diagnostic.md"
    json_path = md_path.with_suffix(".json")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(build_smoke_markdown(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return md_path
