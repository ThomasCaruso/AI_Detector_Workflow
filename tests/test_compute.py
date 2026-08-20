import json
from pathlib import Path

from authorship_shift.ablation import variant_registry
from authorship_shift.compute import estimate_pipeline_calls


CONFIG = {
    "generation": {
        "plans": 4,
        "drafts_per_plan": 1,
        "beam_width": 4,
        "beam_rounds": 1,
        "operators_per_candidate": 2,
        "operators": ["a", "b", "c"],
    }
}


def test_baseline_call_count_matches_direct_pipeline_topology():
    estimate = estimate_pipeline_calls(CONFIG, variant_registry()["baseline"])
    assert estimate["total_model_calls_upper_bound"] == 5
    assert estimate["calls_by_role"]["draft"] == 1
    assert estimate["calls_by_role"]["structure_plan"] == 0


def test_full_pipeline_upper_bound_counts_operator_judging():
    estimate = estimate_pipeline_calls(CONFIG, variant_registry()["full"])
    assert estimate["drafts"] == 4
    assert estimate["operator_children_upper_bound"] == 8
    assert estimate["judged_candidates_upper_bound"] == 16
    assert estimate["total_model_calls_upper_bound"] == 51


def test_smoke_config_has_known_bounded_compute_budget():
    config = json.loads(Path("configs/smoke.json").read_text(encoding="utf-8"))
    registry = variant_registry()
    variants = config["ablation"]["default_variants"]
    per_run = {
        name: estimate_pipeline_calls(config, registry[name])["total_model_calls_upper_bound"]
        for name in variants
    }

    assert per_run == {
        "baseline": 5,
        "planning_revision": 15,
        "full": 21,
    }
    assert sum(per_run.values()) == 41
    assert sum(per_run.values()) * config["ablation"]["max_development_samples"] == 123
    assert config["external_evaluation"]["development_queries_allowed"] == 0
    assert config["external_evaluation"]["milestone_queries_budget"] == 0
