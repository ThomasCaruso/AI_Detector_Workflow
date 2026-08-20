import json
from pathlib import Path

from authorship_shift.ablation import aggregate_by_variant, build_ablation_plan, resolve_variants, run_ablation_suite
from authorship_shift.providers.base import Provider


class FakeProvider(Provider):
    @property
    def identity(self):
        return "fake:model"

    def chat(self, prompt, *, system=None, json_mode=False):
        if "Skill 01" in prompt:
            return json.dumps({"purpose": "explain", "audience": "general", "claims": [{"id": "C1", "proposition": "Distribution matters for products", "importance": "required"}], "immutable_items": [], "non_negotiable_terms": [], "forbidden_inferences": []})
        if "Skill 02" in prompt:
            return json.dumps({"plans": [{"name": "p", "logic": "direct", "opening": "claim", "sections": [], "closing": "end", "distinctive_structural_choices": []}]})
        if "Skill 03" in prompt:
            return "Distribution matters for products because users must discover them."
        if "Skill 04" in prompt:
            return "Users must discover products before adoption. Distribution matters for products."
        if "Skill 05" in prompt:
            return json.dumps({"score": 1.0, "pass": True, "missing_claim_ids": [], "altered_claim_ids": [], "added_claims": [], "certainty_changes": [], "immutable_violations": []})
        if "Skill 06" in prompt:
            return json.dumps({"candidate_minus_source": 0.1, "pass": True, "source": {}, "candidate": {}})
        if "Skill 07" in prompt:
            return json.dumps({"recommended_candidate_ids": [], "rejected": [], "selection_reasoning": "ok"})
        if "Skill 08" in prompt:
            return "Distribution matters for products. Discovery precedes adoption."
        raise AssertionError(prompt[:100])


def test_resolve_variants_rejects_unknown():
    assert resolve_variants("baseline,full")[0].name == "baseline"
    try:
        resolve_variants("not-real")
    except ValueError as exc:
        assert "Unknown ablation variant" in str(exc)
    else:
        raise AssertionError("Expected ValueError")


def test_plan_uses_development_split_only(tmp_path):
    corpus = tmp_path / "corpus"; corpus.mkdir()
    dev = corpus / "dev.txt"; held = corpus / "held.txt"
    dev.write_text("development", encoding="utf-8"); held.write_text("heldout", encoding="utf-8")
    (corpus / "split.json").write_text(json.dumps({"development": [str(dev)], "holdout": [str(held)]}), encoding="utf-8")
    plan = build_ablation_plan(corpus, variants="baseline,full")
    assert plan["sample_count"] == 1
    assert plan["task_count"] == 2
    assert all("dev.txt" in task["source_path"] for task in plan["tasks"])


def test_ablation_suite_runs_and_forces_zero_external_budget(tmp_path):
    corpus = tmp_path / "corpus"; corpus.mkdir()
    (corpus / "sample.txt").write_text("Distribution matters for products.", encoding="utf-8")
    output = tmp_path / "suite"
    base_config = {"generation": {"plans": 1, "drafts_per_plan": 1, "beam_width": 1, "beam_rounds": 0, "operators_per_candidate": 0, "operators": []}, "gates": {"minimum_fidelity": 0.9, "minimum_quality_delta": 0.0, "diversity_weight": 0.2}, "external_evaluation": {"milestone_queries_budget": 5}}
    result = run_ablation_suite(corpus, output, FakeProvider(), base_config=base_config, variants="baseline,planning_only", max_samples=1)
    assert result["planned_runs"] == 2
    assert result["completed_runs"] == 2
    assert (output / "ablation_report.md").exists()
    for row in result["runs"]:
        config = json.loads((Path(row["experiment_root"]) / "config.json").read_text(encoding="utf-8"))
        assert config["external_evaluation"]["milestone_queries_budget"] == 0
        assert row["total_model_calls"] > 0
        assert row["elapsed_seconds"] >= 0
        assert (Path(row["experiment_root"]) / "pipeline_stats.json").exists()
    aggregates = aggregate_by_variant(result["runs"])
    assert {row["variant"] for row in aggregates} == {"baseline", "planning_only"}
    assert all(row["mean_model_calls"] > 0 for row in aggregates)
