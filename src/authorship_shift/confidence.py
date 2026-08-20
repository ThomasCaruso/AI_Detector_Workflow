from __future__ import annotations

from collections import defaultdict
from math import comb
from pathlib import Path
from random import Random
from statistics import mean
from typing import Any
import json


METRICS: dict[str, bool] = {
    "hard_gate_pass_rate": True,
    "mean_fidelity": True,
    "mean_quality_delta": True,
    "mean_structural_distance": True,
    "beam_mean_pair_distance": True,
    "candidate_count": False,
}


def _percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = min(max(q, 0.0), 1.0) * (len(ordered) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def bootstrap_mean_ci(
    values: list[float],
    *,
    confidence: float = 0.95,
    resamples: int = 2000,
    seed: str = "authorship-shift",
) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    if len(values) == 1 or resamples <= 1:
        return values[0], values[0]
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must be between 0 and 1")
    rng = Random(seed)
    n = len(values)
    draws = [mean(values[rng.randrange(n)] for _ in range(n)) for _ in range(resamples)]
    alpha = (1.0 - confidence) / 2.0
    return _percentile(draws, alpha), _percentile(draws, 1.0 - alpha)


def exact_two_sided_sign_test(oriented_deltas: list[float]) -> float:
    nonzero = [d for d in oriented_deltas if abs(d) > 1e-12]
    n = len(nonzero)
    if n == 0:
        return 1.0
    positives = sum(1 for d in nonzero if d > 0)
    tail = min(positives, n - positives)
    probability = sum(comb(n, k) for k in range(tail + 1)) / (2 ** n)
    return min(1.0, 2.0 * probability)


def _index_results(results: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    indexed: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in results:
        variant = str(row.get("variant", ""))
        sample = str(row.get("sample_id", ""))
        if variant and sample:
            indexed[variant][sample] = row
    return indexed


def paired_metric_summary(
    results: list[dict[str, Any]],
    baseline: str,
    challenger: str,
    metric: str,
    *,
    higher_is_better: bool = True,
    confidence: float = 0.95,
    resamples: int = 2000,
    seed: str = "authorship-shift",
) -> dict[str, Any]:
    indexed = _index_results(results)
    shared = sorted(set(indexed.get(baseline, {})) & set(indexed.get(challenger, {})))
    raw_deltas: list[float] = []
    oriented: list[float] = []
    baseline_values: list[float] = []
    challenger_values: list[float] = []
    sign = 1.0 if higher_is_better else -1.0
    for sample in shared:
        a = float(indexed[baseline][sample].get(metric, 0.0) or 0.0)
        b = float(indexed[challenger][sample].get(metric, 0.0) or 0.0)
        delta = b - a
        baseline_values.append(a)
        challenger_values.append(b)
        raw_deltas.append(delta)
        oriented.append(sign * delta)
    ci_low, ci_high = bootstrap_mean_ci(
        oriented,
        confidence=confidence,
        resamples=resamples,
        seed=f"{seed}:{baseline}:{challenger}:{metric}",
    )
    wins = sum(1 for d in oriented if d > 1e-12)
    ties = sum(1 for d in oriented if abs(d) <= 1e-12)
    n = len(oriented)
    return {
        "metric": metric,
        "higher_is_better": higher_is_better,
        "paired_samples": n,
        "baseline_mean": mean(baseline_values) if baseline_values else 0.0,
        "challenger_mean": mean(challenger_values) if challenger_values else 0.0,
        "raw_mean_delta": mean(raw_deltas) if raw_deltas else 0.0,
        "oriented_mean_improvement": mean(oriented) if oriented else 0.0,
        "bootstrap_ci_low": ci_low,
        "bootstrap_ci_high": ci_high,
        "challenger_win_rate": wins / n if n else 0.0,
        "tie_rate": ties / n if n else 0.0,
        "sign_test_p_value": exact_two_sided_sign_test(oriented),
    }


def analyze_confidence(
    suite_dir: str | Path,
    *,
    baseline: str = "baseline",
    confidence: float = 0.95,
    resamples: int = 2000,
    seed: str = "authorship-shift",
) -> dict[str, Any]:
    root = Path(suite_dir)
    payload = json.loads((root / "suite_results.json").read_text(encoding="utf-8"))
    results = list(payload.get("runs", []))
    variants = sorted({str(row.get("variant", "")) for row in results if row.get("variant")})
    if baseline not in variants:
        raise ValueError(f"Baseline variant '{baseline}' is not present in suite results")
    comparisons: list[dict[str, Any]] = []
    for challenger in variants:
        if challenger == baseline:
            continue
        metrics = [
            paired_metric_summary(
                results,
                baseline,
                challenger,
                metric,
                higher_is_better=higher,
                confidence=confidence,
                resamples=resamples,
                seed=seed,
            )
            for metric, higher in METRICS.items()
        ]
        comparisons.append({
            "baseline": baseline,
            "challenger": challenger,
            "paired_samples": max((m["paired_samples"] for m in metrics), default=0),
            "metrics": metrics,
        })
    return {
        "baseline": baseline,
        "confidence": confidence,
        "resamples": resamples,
        "run_count": len(results),
        "variant_count": len(variants),
        "comparisons": comparisons,
        "note": (
            "Bootstrap intervals and sign tests summarize local paired ablation results only. "
            "They do not estimate or predict any proprietary detector score."
        ),
    }


def write_confidence_report(
    suite_dir: str | Path,
    output: str | Path | None = None,
    *,
    baseline: str = "baseline",
    confidence: float = 0.95,
    resamples: int = 2000,
    seed: str = "authorship-shift",
) -> Path:
    root = Path(suite_dir)
    analysis = analyze_confidence(
        root,
        baseline=baseline,
        confidence=confidence,
        resamples=resamples,
        seed=seed,
    )
    path = Path(output) if output else root / "confidence_report.md"
    json_path = root / "confidence.json"
    lines = [
        "# Ablation Confidence Report",
        "",
        analysis["note"],
        "",
        f"Baseline: `{baseline}`. Bootstrap confidence: {confidence:.1%}. Resamples: {resamples}.",
        "",
    ]
    for comparison in analysis["comparisons"]:
        lines += [
            f"## {comparison['challenger']} vs {comparison['baseline']}",
            "",
            "| Metric | Paired n | Oriented mean improvement | Bootstrap CI | Win rate | Sign-test p |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for metric in comparison["metrics"]:
            lines.append(
                f"| `{metric['metric']}` | {metric['paired_samples']} | "
                f"{metric['oriented_mean_improvement']:+.4f} | "
                f"[{metric['bootstrap_ci_low']:+.4f}, {metric['bootstrap_ci_high']:+.4f}] | "
                f"{metric['challenger_win_rate']:.1%} | {metric['sign_test_p_value']:.4f} |"
            )
        lines.append("")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    return path
