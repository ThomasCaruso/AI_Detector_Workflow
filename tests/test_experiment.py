from authorship_shift.experiment import Experiment
from authorship_shift.models import Candidate, ExternalResult


def test_external_requires_freeze_and_enforces_budget(tmp_path):
    exp = Experiment(tmp_path / "e")
    exp.initialize(
        "x",
        "source",
        {"external_evaluation": {"milestone_queries_budget": 1, "require_frozen_candidate": True}},
    )
    cand = Candidate(text="candidate", stage="manual")
    exp.add_candidate(cand)

    try:
        exp.record_external(ExternalResult(detector="Pangram 4", label="AI", score=100, candidate_id=cand.id))
    except RuntimeError as exc:
        assert "not frozen" in str(exc)
    else:
        assert False, "unfrozen candidate should be rejected"

    exp.freeze_candidate(cand.id)
    exp.record_external(ExternalResult(detector="Pangram 4", label="AI", score=100, candidate_id=cand.id))

    try:
        exp.record_external(ExternalResult(detector="Pangram 4", label="AI", score=100, candidate_id=cand.id))
    except RuntimeError:
        return
    assert False, "budget should be enforced"
