from authorship_shift.experiment import Experiment
from authorship_shift.models import Candidate
from authorship_shift.report import build_markdown_report


def test_report_contains_budget(tmp_path):
    exp = Experiment(tmp_path / "e")
    exp.initialize("demo", "source text", {"external_evaluation": {"milestone_queries_budget": 5}})
    exp.add_candidate(Candidate(text="candidate text", stage="manual"))
    report = build_markdown_report(exp.root)
    assert "External detector queries used" in report
    assert "0 / 5" in report
