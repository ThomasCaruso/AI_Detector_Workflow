from authorship_shift.experiment import Experiment
from authorship_shift.models import Candidate, ExternalResult, read_json
from authorship_shift.provenance import audit_experiment, sha256_text


def test_experiment_hashes_and_external_record_are_bound_to_frozen_text(tmp_path):
    exp = Experiment(tmp_path / "e")
    exp.initialize(
        "x", "source",
        {"external_evaluation": {"milestone_queries_budget": 1, "require_frozen_candidate": True}},
    )
    cand = Candidate(text="candidate", stage="manual")
    exp.add_candidate(cand)
    exp.freeze_candidate(cand.id)
    out = exp.record_external(ExternalResult(detector="Pangram 4", label="AI", score=100, candidate_id=cand.id))

    manifest = exp.manifest()
    assert manifest["source_sha256"] == sha256_text("source")
    stored = exp.get_candidate(cand.id)
    assert stored.metadata["content_sha256"] == sha256_text("candidate")
    assert stored.metadata["frozen_sha256"] == sha256_text("candidate")
    result = read_json(out)
    assert result["candidate_sha256"] == sha256_text("candidate")
    assert audit_experiment(exp.root)["ok"] is True


def test_integrity_audit_detects_frozen_text_tampering(tmp_path):
    exp = Experiment(tmp_path / "e")
    exp.initialize("x", "source", {"external_evaluation": {"milestone_queries_budget": 1}})
    cand = Candidate(text="candidate", stage="manual")
    exp.add_candidate(cand)
    frozen = exp.freeze_candidate(cand.id)
    frozen.write_text("tampered", encoding="utf-8")
    audit = audit_experiment(exp.root)
    assert audit["ok"] is False
    assert any("frozen text differs" in error for error in audit["errors"])
