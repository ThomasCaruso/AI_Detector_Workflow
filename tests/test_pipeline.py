import json
from authorship_shift.experiment import Experiment
from authorship_shift.pipeline import run_pipeline
from authorship_shift.providers.base import Provider


class FakeProvider(Provider):
    @property
    def identity(self):
        return "fake:model"

    def chat(self, prompt, *, system=None, json_mode=False):
        if "Skill 01" in prompt:
            return json.dumps({
                "purpose": "explain",
                "audience": "general",
                "claims": [{"id": "C1", "proposition": "Distribution matters for products", "importance": "required"}],
                "immutable_items": [],
                "non_negotiable_terms": [],
                "forbidden_inferences": [],
            })
        if "Skill 02" in prompt:
            return json.dumps({"plans": [{"name": "p", "logic": "direct", "opening": "claim", "sections": [{"function": "explain", "claim_ids": ["C1"], "notes": ""}], "closing": "end", "distinctive_structural_choices": []}]})
        if "Skill 03" in prompt:
            return "Distribution matters for products because strong products still need users to discover them."
        if "Skill 04" in prompt:
            return "Strong products still need discovery. Distribution matters for products because users cannot adopt what they never encounter."
        if "Skill 05" in prompt:
            return json.dumps({"score": 1.0, "pass": True, "required_claims_total": 1, "required_claims_preserved": 1, "missing_claim_ids": [], "altered_claim_ids": [], "added_claims": [], "certainty_changes": [], "immutable_violations": [], "reason": "ok"})
        if "Skill 06" in prompt:
            return json.dumps({"source": {}, "candidate": {}, "candidate_minus_source": 0.2, "pass": True, "main_improvements": [], "main_regressions": []})
        if "Skill 07" in prompt:
            return json.dumps({"recommended_candidate_ids": [], "rejected": [], "selection_reasoning": "ok"})
        if "Skill 08" in prompt:
            return "Distribution matters for products. Users cannot adopt a product they never discover, even when the product itself is strong."
        raise AssertionError(prompt[:100])


def test_pipeline_runs_with_beam(tmp_path):
    exp = Experiment(tmp_path / "e")
    exp.initialize("x", "Distribution matters for products.", {"external_evaluation": {"milestone_queries_budget": 5}})
    result = run_pipeline(
        exp,
        FakeProvider(),
        plans_n=1,
        drafts_per_plan=1,
        beam_width=2,
        beam_rounds=1,
        operators=["claim_first"],
        operators_per_candidate=1,
    )
    assert len(result.candidates) >= 3
    assert result.beam_ids
    assert (exp.root / "ranking.json").exists()
