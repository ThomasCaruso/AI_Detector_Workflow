from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import mean
from typing import Any
import json


MAXIMIZE = (
    "hard_gate_pass_rate",
    "mean_fidelity",
    "mean_quality_delta",
    "mean_structural_distance",
    "beam_mean_pair_distance",
)
MINIMIZE = ("candidate_count",)


@dataclass(frozen=True)
class VariantDecision:
    variant: str
    runs: int
    hard_gate_pass_rate: float
    mean_fidelity: float
    mean_quality_delta: float
    mean_structural_distance: float
    beam_mean_pair_distance: float
    mean_candidate_count: float
    coverage: float
    pareto: bool = False
    utility: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _avg(rows: list[dict[str, Any]], key: str) -> float:
    vals = [float(r.get(key, 0.0) or 0.0) for r in rows]
    return mean(vals) if vals else 0.0


def _normalize(values: dict[str, float], *, higher_is_better: bool = True) -> dict[str, float]:
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    if hi == lo:
        return {k: 1.0 for k in values}
    norm = {k: (v - lo) / (hi - lo) for k, v in values.items()}
    if not higher_is_better:
        norm = {k: 1.0 - v for k, v in norm.items()}
    return norm


def aggregate_runs(results: list[dict[str, Any]], planned_samples: int | None = None) -> list[VariantDecision]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in results:
        grouped[str(row.get("variant", "unknown"))].append(row)
    if planned_samples is None:
        planned_samples = len({str(r.get("sample_id", "")) for r in results}) or 1

    base: dict[str, dict[str, float]] = {}
    for variant, rows in grouped.items():
        base[variant] = {
            "runs": float(len(rows)),
            "hard_gate_pass_rate": _avg(rows, "hard_gate_pass_rate"),
            "mean_fidelity": _avg(rows, "mean_fidelity"),
            "mean_quality_delta": _avg(rows, "mean_quality_delta"),
            "mean_structural_distance": _avg(rows, "mean_structural_distance"),
            "beam_mean_pair_distance": _avg(rows, "beam_mean_pair_distance"),
            "mean_candidate_count": _avg(rows, "candidate_count"),
            "coverage": min(1.0, len(rows) / max(1, planned_samples)),
        }

    normalized: dict[str, dict[str, float]] = {}
    for metric in MAXIMIZE:
        normalized[metric] = _normalize({v: d[metric] for v, d in base.items()}, higher_is_better=True)
    normalized["mean_candidate_count"] = _normalize(
        {v: d["mean_candidate_count"] for v, d in base.items()}, higher_is_better=False
    )

    # Fidelity and gate survival dominate the decision. Structural movement matters,
    # but it cannot compensate for damaged content or degraded writing.
    weights = {
        "hard_gate_pass_rate": 0.30,
        "mean_fidelity": 0.25,
        "mean_quality_delta": 0.20,
        "mean_structural_distance": 0.10,
        "beam_mean_pair_distance": 0.05,
        "mean_candidate_count": 0.10,
    }

    utilities: dict[str, float] = {}
    for variant, data in base.items():
        score = sum(weights[m] * normalized[m][variant] for m in weights)
        utilities[variant] = score * data["coverage"]

    pareto_variants = _pareto_variants(base)
    decisions = []
    for variant, data in base.items():
        decisions.append(
            VariantDecision(
                variant=variant,
                runs=int(data["runs"]),
                hard_gate_pass_rate=data["hard_gate_pass_rate"],
                mean_fidelity=data["mean_fidelity"],
                mean_quality_delta=data["mean_quality_delta"],
                mean_structural_distance=data["mean_structural_distance"],
                beam_mean_pair_distance=data["beam_mean_pair_distance"],
                mean_candidate_count=data["mean_candidate_count"],
                coverage=data["coverage"],
                pareto=variant in pareto_variants,
                utility=utilities[variant],
            )
        )
    return sorted(decisions, key=lambda d: (d.utility, d.pareto, d.coverage), reverse=True)


def _dominates(a: dict[str, float], b: dict[str, float]) -> bool:
    weakly_better = True
    strictly_better = False
    for metric in MAXIMIZE:
        if a[metric] < b[metric]:
            weakly_better = False
            break
        strictly_better |= a[metric] > b[metric]
    if weakly_better:
        if a["mean_candidate_count"] > b["mean_candidate_count"]:
            weakly_better = False
        else:
            strictly_better |= a["mean_candidate_count"] < b["mean_candidate_count"]
    return weakly_better and strictly_better


def _pareto_variants(base: dict[str, dict[str, float]]) -> set[str]:
    front: set[str] = set()
    for name, row in base.items():
        if not any(other != name and _dominates(other_row, row) for other, other_row in base.items()):
            front.add(name)
    return front


def paired_delta(results: list[dict[str, Any]], baseline: str, challenger: str) -> dict[str, Any]:
    by_variant: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in results:
        by_variant[str(row.get("variant", ""))][str(row.get("sample_id", ""))] = row
    shared = sorted(set(by_variant.get(baseline, {})) & set(by_variant.get(challenger, {})))
    metrics = (
        "hard_gate_pass_rate",
        "mean_fidelity",
        "mean_quality_delta",
        "mean_structural_distance",
        "beam_mean_pair_distance",
        "candidate_count",
    )
    deltas: dict[str, list[float]] = {m: [] for m in metrics}
    wins: dict[str, int] = {m: 0 for m in metrics}
    for sid in shared:
        a = by_variant[baseline][sid]
        b = by_variant[challenger][sid]
        for metric in metrics:
            delta = float(b.get(metric, 0.0) or 0.0) - float(a.get(metric, 0.0) or 0.0)
            deltas[metric].append(delta)
            if (metric == "candidate_count" and delta < 0) or (metric != "candidate_count" and delta > 0):
                wins[metric] += 1
    return {
        "baseline": baseline,
        "challenger": challenger,
        "paired_samples": len(shared),
        "mean_delta": {m: (mean(v) if v else 0.0) for m, v in deltas.items()},
        "challenger_win_rate": {m: (wins[m] / len(shared) if shared else 0.0) for m in metrics},
    }


def recommend_validation_slots(decisions: list[VariantDecision], slots: int = 3) -> list[dict[str, Any]]:
    if slots < 1:
        return []
    eligible = [d for d in decisions if d.coverage >= 0.999 and d.mean_quality_delta >= 0.0]
    if not eligible:
        eligible = [d for d in decisions if d.mean_quality_delta >= 0.0]
    if not eligible:
        eligible = list(decisions)

    chosen: list[VariantDecision] = []
    baseline = next((d for d in eligible if d.variant == "baseline"), None)
    if baseline is not None and len(chosen) < slots:
        chosen.append(baseline)

    for d in eligible:
        if len(chosen) >= slots:
            break
        if d.variant not in {x.variant for x in chosen} and d.pareto:
            chosen.append(d)

    for d in eligible:
        if len(chosen) >= slots:
            break
        if d.variant not in {x.variant for x in chosen}:
            chosen.append(d)

    return [
        {
            "slot": i + 1,
            "variant": d.variant,
            "reason": (
                "control baseline" if d.variant == "baseline" else
                "Pareto-efficient local candidate" if d.pareto else
                "next-highest local utility"
            ),
            "utility": d.utility,
            "coverage": d.coverage,
            "quality_delta": d.mean_quality_delta,
            "fidelity": d.mean_fidelity,
        }
        for i, d in enumerate(chosen)
    ]


def analyze_suite(suite_dir: str | Path, slots: int = 3) -> dict[str, Any]:
    root = Path(suite_dir)
    payload = json.loads((root / "suite_results.json").read_text(encoding="utf-8"))
    results = list(payload.get("runs", []))
    plan_path = root / "suite_plan.json"
    planned_samples = None
    if plan_path.exists():
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        planned_samples = int(plan.get("sample_count", 0) or 0) or None
    decisions = aggregate_runs(results, planned_samples=planned_samples)
    baseline_name = "baseline" if any(d.variant == "baseline" for d in decisions) else (decisions[-1].variant if decisions else "")
    paired = [paired_delta(results, baseline_name, d.variant) for d in decisions if d.variant != baseline_name]
    return {
        "run_count": len(results),
        "variant_count": len(decisions),
        "baseline": baseline_name,
        "ranking": [d.to_dict() for d in decisions],
        "paired_vs_baseline": paired,
        "recommended_validation_slots": recommend_validation_slots(decisions, slots=slots),
        "note": "This decision layer uses only local fidelity, quality, structure, diversity, and compute diagnostics. It does not predict any proprietary detector score.",
    }


def write_decision_report(suite_dir: str | Path, output: str | Path | None = None, slots: int = 3) -> Path:
    root = Path(suite_dir)
    analysis = analyze_suite(root, slots=slots)
    path = Path(output) if output else root / "decision_report.md"
    lines = [
        "# Ablation Decision Report",
        "",
        analysis["note"],
        "",
        "## Local ranking",
        "",
        "| Rank | Variant | Pareto | Coverage | Gate pass | Fidelity | Quality Δ | Structural Δ | Beam diversity | Mean candidates | Utility |",
        "|---:|---|:---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for idx, row in enumerate(analysis["ranking"], 1):
        lines.append(
            f"| {idx} | {row['variant']} | {'yes' if row['pareto'] else 'no'} | {row['coverage']:.1%} | "
            f"{row['hard_gate_pass_rate']:.3f} | {row['mean_fidelity']:.3f} | {row['mean_quality_delta']:+.3f} | "
            f"{row['mean_structural_distance']:.3f} | {row['beam_mean_pair_distance']:.3f} | {row['mean_candidate_count']:.1f} | {row['utility']:.3f} |"
        )
    lines += ["", "## Suggested scarce validation slots", ""]
    for slot in analysis["recommended_validation_slots"]:
        lines.append(f"- **Slot {slot['slot']} — {slot['variant']}**: {slot['reason']}; utility {slot['utility']:.3f}, fidelity {slot['fidelity']:.3f}, quality Δ {slot['quality_delta']:+.3f}.")
    lines += ["", "## Paired changes vs baseline", ""]
    for row in analysis["paired_vs_baseline"]:
        lines.append(f"### {row['challenger']} vs {row['baseline']} ({row['paired_samples']} paired samples)")
        lines.append("")
        for metric, delta in row["mean_delta"].items():
            lines.append(f"- `{metric}` mean Δ: {delta:+.4f}; challenger win rate: {row['challenger_win_rate'][metric]:.1%}")
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    (root / "decision.json").write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    return path
