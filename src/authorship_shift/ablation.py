from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from statistics import mean
from typing import Any, Iterable
import time

from .diversity import summarize_diversity
from .experiment import Experiment
from .models import read_json, write_json
from .pipeline import run_pipeline
from .providers.base import Provider


@dataclass(frozen=True)
class AblationVariant:
    name: str
    description: str
    use_planning: bool
    use_global_revision: bool
    use_operators: bool
    use_diversity: bool
    generator_pool: str = "all"
    plans_n: int | None = None
    beam_width: int | None = None
    beam_rounds: int | None = None
    operators_per_candidate: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_VARIANTS: tuple[AblationVariant, ...] = (
    AblationVariant("baseline", "Direct single-model drafting with no explicit planning, revision, operators, or diversity search.", False, False, False, False, "single", 1, 1, 0, 0),
    AblationVariant("planning_only", "Adds explicit document planning while keeping a single generator and no revision/operator stages.", True, False, False, False, "single"),
    AblationVariant("generator_diversity", "Planning plus heterogeneous generator families and diversity-aware beam selection, without revision/operators.", True, False, False, True, "all"),
    AblationVariant("planning_revision", "Planning, heterogeneous generators, global revision, and diversity selection; operators disabled.", True, True, False, True, "all"),
    AblationVariant("planning_operators", "Planning, heterogeneous generators, and operator expansion without the global revision stage.", True, False, True, True, "all"),
    AblationVariant("full_no_diversity", "Full planning/revision/operator pipeline with diversity contribution disabled during beam selection.", True, True, True, False, "all"),
    AblationVariant("full", "Full planning, heterogeneous generation, global revision, operators, and diversity-aware beam search.", True, True, True, True, "all"),
)


def variant_registry() -> dict[str, AblationVariant]:
    return {variant.name: variant for variant in DEFAULT_VARIANTS}


def resolve_variants(names: str | Iterable[str] | None) -> list[AblationVariant]:
    registry = variant_registry()
    if names is None:
        return list(DEFAULT_VARIANTS)
    if isinstance(names, str):
        requested = [name.strip() for name in names.split(",") if name.strip()]
    else:
        requested = [str(name).strip() for name in names if str(name).strip()]
    if not requested:
        return list(DEFAULT_VARIANTS)
    unknown = [name for name in requested if name not in registry]
    if unknown:
        raise ValueError("Unknown ablation variant(s): " + ", ".join(unknown) + ". Available: " + ", ".join(registry))
    return [registry[name] for name in requested]


def _resolve_split_entry(corpus_root: Path, entry: str) -> Path:
    raw = Path(entry)
    if raw.is_absolute():
        candidates = (raw,)
    else:
        candidates = (corpus_root / raw, corpus_root / raw.name, raw)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Corpus split entry cannot be resolved: {entry}")


def development_files(corpus_dir: str | Path, *, split_file: str | Path | None = None, max_samples: int | None = None) -> list[Path]:
    root = Path(corpus_dir).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Corpus directory does not exist: {root}")
    split_path = Path(split_file) if split_file else root / "split.json"
    if split_path.exists():
        entries = read_json(split_path).get("development", [])
        files = [_resolve_split_entry(root, entry) for entry in entries]
    else:
        files = sorted(path.resolve() for path in root.rglob("*.txt") if path.is_file())
    files = list(dict.fromkeys(files))
    if max_samples is not None:
        if max_samples < 1:
            raise ValueError("max_samples must be at least 1")
        files = files[:max_samples]
    if not files:
        raise ValueError(f"No development .txt samples found under {root}")
    return files


def _portable_source_ref(corpus_root: Path, path: Path) -> str:
    root = corpus_root.resolve()
    resolved = path.resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        # Legacy split files may point outside the declared corpus root. Preserve support
        # for those inputs, but keep normal corpus entries machine-independent.
        return str(resolved)


def _sample_id(path: Path, *, corpus_root: Path) -> str:
    stem = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in path.stem).strip("-") or "sample"
    source_ref = _portable_source_ref(corpus_root, path)
    digest = sha256(source_ref.encode("utf-8")).hexdigest()[:8]
    return f"{stem}-{digest}"


def build_ablation_plan(corpus_dir: str | Path, *, variants: str | Iterable[str] | None = None, split_file: str | Path | None = None, max_samples: int | None = None) -> dict[str, Any]:
    corpus_root = Path(corpus_dir).resolve()
    files = development_files(corpus_root, split_file=split_file, max_samples=max_samples)
    resolved_variants = resolve_variants(variants)
    tasks = []
    for source_path in files:
        source_ref = _portable_source_ref(corpus_root, source_path)
        sample_id = _sample_id(source_path, corpus_root=corpus_root)
        for variant in resolved_variants:
            tasks.append({"sample_id": sample_id, "source_path": source_ref, "variant": variant.to_dict()})
    return {
        "created_at": time.time(),
        "corpus_dir": str(corpus_root),
        "split_file": str(Path(split_file).resolve()) if split_file else None,
        "sample_count": len(files),
        "variant_count": len(resolved_variants),
        "task_count": len(tasks),
        "variants": [variant.to_dict() for variant in resolved_variants],
        "tasks": tasks,
    }


def write_ablation_plan(output_dir: str | Path, plan: dict[str, Any]) -> Path:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = root / "suite_plan.json"
    write_json(path, plan)
    return path


def _passes_gates(row: dict[str, Any], gates: dict[str, Any]) -> bool:
    fidelity = row.get("fidelity", {}) or {}
    quality = row.get("quality", {}) or {}
    precheck = row.get("claim_precheck", {}) or {}
    if float(fidelity.get("score", 0.0)) < float(gates.get("minimum_fidelity", 0.96)):
        return False
    if fidelity.get("pass") is False:
        return False
    if float(quality.get("candidate_minus_source", -999.0)) < float(gates.get("minimum_quality_delta", 0.0)):
        return False
    if quality.get("pass") is False:
        return False
    return not precheck.get("immutable_items_missing")


def _safe_mean(values: list[float]) -> float:
    return mean(values) if values else 0.0


def summarize_run(experiment_root: str | Path) -> dict[str, Any]:
    root = Path(experiment_root)
    manifest = read_json(root / "manifest.json")
    config = read_json(root / "config.json")
    ranking = read_json(root / "ranking.json") if (root / "ranking.json").exists() else []
    selection = read_json(root / "selection.json") if (root / "selection.json").exists() else {}
    pipeline_stats = read_json(root / "pipeline_stats.json") if (root / "pipeline_stats.json").exists() else {}
    candidates = []
    for cid in manifest.get("candidate_ids", []):
        path = root / "candidates" / f"{cid}.json"
        if path.exists():
            candidates.append(read_json(path))
    gates = config.get("gates", {})
    fidelity_scores = [float((row.get("fidelity") or {}).get("score", 0.0)) for row in ranking]
    quality_deltas = [float((row.get("quality") or {}).get("candidate_minus_source", 0.0)) for row in ranking]
    structural = [float(row.get("structural_distance", 0.0) or 0.0) for row in ranking]
    hard_passes = sum(1 for row in ranking if _passes_gates(row, gates))
    stage_counts: dict[str, int] = {}
    models: set[str] = set()
    texts: list[str] = []
    for candidate in candidates:
        stage = candidate.get("stage", "unknown")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
        md = candidate.get("metadata", {}) or {}
        for key in ("generator_model", "reviser_model", "judge_model"):
            if md.get(key):
                models.add(str(md[key]))
        if candidate.get("text"):
            texts.append(candidate["text"])
    beam_ids = list(selection.get("deterministic_beam_ids", [])) if isinstance(selection, dict) else []
    beam_diversity = (selection.get("beam_diversity") or {}) if isinstance(selection, dict) else {}
    all_diversity = summarize_diversity(texts).to_dict()
    return {
        "title": manifest.get("title", root.name),
        "experiment_root": str(root.resolve()),
        "candidate_count": len(candidates),
        "stage_counts": stage_counts,
        "models": sorted(models),
        "hard_gate_pass_count": hard_passes,
        "hard_gate_pass_rate": hard_passes / len(ranking) if ranking else 0.0,
        "mean_fidelity": _safe_mean(fidelity_scores),
        "mean_quality_delta": _safe_mean(quality_deltas),
        "mean_structural_distance": _safe_mean(structural),
        "max_structural_distance": max(structural) if structural else 0.0,
        "beam_size": len(beam_ids),
        "beam_mean_pair_distance": float(beam_diversity.get("mean_pair_distance", 0.0) or 0.0),
        "all_mean_pair_distance": float(all_diversity.get("mean_pair_distance", 0.0) or 0.0),
        "total_model_calls": int(pipeline_stats.get("total_model_calls", 0) or 0),
        "elapsed_seconds": float(pipeline_stats.get("elapsed_seconds", 0.0) or 0.0),
        "call_counts": dict(pipeline_stats.get("call_counts", {}) or {}),
        "external_queries_used": int(manifest.get("external_queries_used", 0)),
    }


def _variant_settings(base_config: dict[str, Any], variant: AblationVariant) -> dict[str, Any]:
    gen = base_config.get("generation", {})
    return {
        "plans_n": int(variant.plans_n if variant.plans_n is not None else gen.get("plans", 4)),
        "drafts_per_plan": int(gen.get("drafts_per_plan", 1)),
        "beam_width": int(variant.beam_width if variant.beam_width is not None else gen.get("beam_width", 4)),
        "beam_rounds": int(variant.beam_rounds if variant.beam_rounds is not None else gen.get("beam_rounds", 1)),
        "operators": list(gen.get("operators", [])),
        "operators_per_candidate": int(variant.operators_per_candidate if variant.operators_per_candidate is not None else gen.get("operators_per_candidate", 2)),
        "use_planning": variant.use_planning,
        "use_global_revision": variant.use_global_revision,
        "use_operators": variant.use_operators,
        "use_diversity": variant.use_diversity,
    }


def run_ablation_suite(corpus_dir: str | Path, output_dir: str | Path, providers: Provider | list[Provider], *, judge_provider: Provider | None = None, base_config: dict[str, Any] | None = None, variants: str | Iterable[str] | None = None, split_file: str | Path | None = None, max_samples: int | None = None, max_runs: int | None = None, resume: bool = True) -> dict[str, Any]:
    provider_list = providers if isinstance(providers, list) else [providers]
    if not provider_list:
        raise ValueError("At least one provider is required")
    judge = judge_provider or provider_list[0]
    config = deepcopy(base_config or {})
    corpus_root = Path(corpus_dir).resolve()
    plan = build_ablation_plan(corpus_root, variants=variants, split_file=split_file, max_samples=max_samples)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    write_ablation_plan(root, plan)
    results_path = root / "suite_results.json"
    existing: dict[tuple[str, str], dict[str, Any]] = {}
    if resume and results_path.exists():
        for row in read_json(results_path).get("runs", []):
            existing[(row.get("sample_id", ""), row.get("variant", ""))] = row
    results: list[dict[str, Any]] = []
    completed_this_call = 0
    for task in plan["tasks"]:
        if max_runs is not None and completed_this_call >= max_runs:
            break
        sample_id = task["sample_id"]
        variant = AblationVariant(**task["variant"])
        key = (sample_id, variant.name)
        run_root = root / "runs" / sample_id / variant.name
        if resume and (run_root / "ranking.json").exists():
            # Re-summarize completed runs so newly added instrumentation is reflected in
            # suite_results.json rather than preserving stale summaries indefinitely.
            summary = summarize_run(run_root)
            summary.update({"sample_id": sample_id, "source_path": task["source_path"], "variant": variant.name, "variant_description": variant.description, "variant_settings": variant.to_dict()})
            results.append(summary)
            continue
        source_path = _resolve_split_entry(corpus_root, task["source_path"])
        source = source_path.read_text(encoding="utf-8")
        run_config = deepcopy(config)
        run_config.setdefault("external_evaluation", {})
        run_config["external_evaluation"]["development_queries_allowed"] = 0
        run_config["external_evaluation"]["milestone_queries_budget"] = 0
        run_config["ablation_variant"] = variant.to_dict()
        exp = Experiment(run_root)
        if exp.manifest_path.exists():
            if not resume:
                raise FileExistsError(f"Ablation run already exists: {run_root}")
        else:
            exp.initialize(f"{source_path.stem} / {variant.name}", source, run_config)
        selected_providers = provider_list[:1] if variant.generator_pool == "single" else provider_list
        settings = _variant_settings(run_config, variant)
        gates = run_config.get("gates", {})
        run_pipeline(exp, selected_providers, judge_provider=judge, diversity_weight=float(gates.get("diversity_weight", 0.25)), gates=gates, **settings)
        summary = summarize_run(run_root)
        summary.update({"sample_id": sample_id, "source_path": task["source_path"], "variant": variant.name, "variant_description": variant.description, "variant_settings": variant.to_dict()})
        write_json(run_root / "ablation_summary.json", summary)
        results.append(summary)
        completed_this_call += 1
        write_json(results_path, {"updated_at": time.time(), "planned_runs": plan["task_count"], "completed_runs": len(results), "runs": results})
    seen = {(row.get("sample_id", ""), row.get("variant", "")) for row in results}
    for key, row in existing.items():
        if key not in seen:
            results.append(row)
    payload = {"updated_at": time.time(), "planned_runs": plan["task_count"], "completed_runs": len(results), "runs": sorted(results, key=lambda row: (row.get("sample_id", ""), row.get("variant", "")))}
    write_json(results_path, payload)
    write_ablation_report(root)
    return payload


def aggregate_by_variant(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in results:
        grouped.setdefault(str(row.get("variant", "unknown")), []).append(row)
    aggregates = []
    for variant, rows in sorted(grouped.items()):
        aggregates.append({
            "variant": variant,
            "runs": len(rows),
            "mean_hard_gate_pass_rate": _safe_mean([float(r.get("hard_gate_pass_rate", 0.0)) for r in rows]),
            "mean_fidelity": _safe_mean([float(r.get("mean_fidelity", 0.0)) for r in rows]),
            "mean_quality_delta": _safe_mean([float(r.get("mean_quality_delta", 0.0)) for r in rows]),
            "mean_structural_distance": _safe_mean([float(r.get("mean_structural_distance", 0.0)) for r in rows]),
            "mean_beam_pair_distance": _safe_mean([float(r.get("beam_mean_pair_distance", 0.0)) for r in rows]),
            "mean_candidate_count": _safe_mean([float(r.get("candidate_count", 0.0)) for r in rows]),
            "mean_model_calls": _safe_mean([float(r.get("total_model_calls", 0.0)) for r in rows]),
            "mean_elapsed_seconds": _safe_mean([float(r.get("elapsed_seconds", 0.0)) for r in rows]),
            "external_queries_used": sum(int(r.get("external_queries_used", 0)) for r in rows),
        })
    return aggregates


def build_ablation_markdown(output_dir: str | Path) -> str:
    root = Path(output_dir)
    plan = read_json(root / "suite_plan.json")
    results = read_json(root / "suite_results.json").get("runs", []) if (root / "suite_results.json").exists() else []
    aggregates = aggregate_by_variant(results)
    lines = [
        "# Ablation Suite Report", "", "## Status", "",
        f"- Development samples: **{plan.get('sample_count', 0)}**",
        f"- Variants: **{plan.get('variant_count', 0)}**",
        f"- Planned runs: **{plan.get('task_count', 0)}**",
        f"- Completed runs: **{len(results)}**",
        f"- External detector queries consumed by suite: **{sum(int(r.get('external_queries_used', 0)) for r in results)}**",
        "", "## Aggregate comparison", "",
        "| Variant | Runs | Gate pass | Fidelity | Quality Δ | Structural shift | Beam diversity | Candidates/run | Model calls/run | Runtime/run s |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in aggregates:
        lines.append(
            "| {variant} | {runs} | {gate:.3f} | {fid:.3f} | {quality:.3f} | {struct:.3f} | {div:.3f} | {cand:.1f} | {calls:.1f} | {elapsed:.1f} |".format(
                variant=row["variant"], runs=row["runs"], gate=row["mean_hard_gate_pass_rate"],
                fid=row["mean_fidelity"], quality=row["mean_quality_delta"], struct=row["mean_structural_distance"],
                div=row["mean_beam_pair_distance"], cand=row["mean_candidate_count"], calls=row["mean_model_calls"],
                elapsed=row["mean_elapsed_seconds"],
            )
        )
    lines.extend(["", "## Interpretation rules", "", "- These comparisons isolate pipeline components; they do not estimate any proprietary detector's score.", "- Fidelity and quality remain hard constraints. More structural movement is not automatically better.", "- Model-call counts are measured from each completed local pipeline run; wall-clock time is hardware/load dependent.", "- Development runs are configured with an external-query budget of zero.", "- Held-out corpus samples should remain untouched until a pipeline configuration is frozen.", "", "## Variants", ""])
    for variant in plan.get("variants", []):
        lines.append(f"- **{variant.get('name')}** — {variant.get('description')}")
    lines.append("")
    return "\n".join(lines)


def write_ablation_report(output_dir: str | Path, output: str | Path | None = None) -> Path:
    root = Path(output_dir)
    path = Path(output) if output else root / "ablation_report.md"
    path.write_text(build_ablation_markdown(root), encoding="utf-8")
    return path
