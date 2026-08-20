from __future__ import annotations

import json

from authorship_shift.decision import aggregate_runs, analyze_suite, paired_delta, recommend_validation_slots


def _row(sample, variant, gate, fidelity, quality, structural, diversity, candidates):
    return {
        "sample_id": sample,
        "variant": variant,
        "hard_gate_pass_rate": gate,
        "mean_fidelity": fidelity,
        "mean_quality_delta": quality,
        "mean_structural_distance": structural,
        "beam_mean_pair_distance": diversity,
        "candidate_count": candidates,
    }


def test_pareto_and_utility_preserve_quality_priority():
    rows = [
        _row("a", "baseline", 1.0, 0.99, 0.10, 0.05, 0.02, 2),
        _row("b", "baseline", 1.0, 0.99, 0.10, 0.04, 0.02, 2),
        _row("a", "full", 1.0, 0.99, 0.30, 0.40, 0.25, 8),
        _row("b", "full", 1.0, 0.99, 0.25, 0.35, 0.22, 8),
        _row("a", "bad_shift", 0.2, 0.70, -0.50, 0.90, 0.80, 4),
        _row("b", "bad_shift", 0.2, 0.70, -0.40, 0.95, 0.82, 4),
    ]
    decisions = aggregate_runs(rows, planned_samples=2)
    names = [d.variant for d in decisions]
    assert names.index("full") < names.index("bad_shift")
    full = next(d for d in decisions if d.variant == "full")
    assert full.pareto


def test_paired_delta_matches_shared_samples():
    rows = [
        _row("a", "baseline", 1, .98, .1, .1, .1, 2),
        _row("a", "full", 1, .99, .3, .4, .3, 8),
        _row("b", "baseline", 1, .98, .1, .1, .1, 2),
        _row("b", "full", 1, .99, .2, .3, .2, 8),
    ]
    out = paired_delta(rows, "baseline", "full")
    assert out["paired_samples"] == 2
    assert out["mean_delta"]["mean_quality_delta"] > 0
    assert out["challenger_win_rate"]["mean_structural_distance"] == 1.0


def test_validation_slots_include_control_when_available():
    rows = [
        _row("a", "baseline", 1, .99, .1, .1, .1, 2),
        _row("a", "full", 1, .99, .2, .3, .2, 7),
    ]
    decisions = aggregate_runs(rows, planned_samples=1)
    slots = recommend_validation_slots(decisions, slots=2)
    assert slots[0]["variant"] == "baseline"
    assert {s["variant"] for s in slots} == {"baseline", "full"}


def test_analyze_suite_writes_no_external_assumptions(tmp_path):
    rows = [
        _row("a", "baseline", 1, .99, .1, .1, .1, 2),
        _row("a", "full", 1, .99, .2, .3, .2, 7),
    ]
    (tmp_path / "suite_results.json").write_text(json.dumps({"runs": rows}), encoding="utf-8")
    (tmp_path / "suite_plan.json").write_text(json.dumps({"sample_count": 1}), encoding="utf-8")
    out = analyze_suite(tmp_path, slots=2)
    assert out["run_count"] == 2
    assert "does not predict" in out["note"]
    assert len(out["recommended_validation_slots"]) == 2
