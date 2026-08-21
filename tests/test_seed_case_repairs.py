import json
from pathlib import Path

from authorship_shift.candidate_lab import extract_immutables
from authorship_shift.manual_batch import render_prompt

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "engine_v2_seed_cases.json"


def _case(case_id: str) -> dict:
    payload = json.loads(CASES.read_text(encoding="utf-8"))
    return next(case for case in payload["cases"] if case["id"] == case_id)


def test_professional_case_fixes_document_furniture():
    case = _case("professional_email_001")
    assert case["revision"] == 2
    task = case["task"].lower()
    assert "body" in task
    assert "subject line" in task
    assert "greeting" in task
    assert "sign-off" in task

    prompt = render_prompt(case, "direct-plain", "Use plain prose.")
    assert "Return only the body text" in prompt


def test_professional_case_has_real_checkable_atlas_and_dates():
    case = _case("professional_email_001")
    immutables = extract_immutables(case["source"])
    assert "Atlas" in immutables
    assert "The Atlas" not in immutables
    assert {"14", "16", "17"}.issubset(set(immutables))


def test_analytical_case_has_nonvacuous_hypothetical_constraints():
    case = _case("competition_innovation_001")
    assert case["revision"] == 2
    immutables = extract_immutables(case["source"])
    assert "18" in immutables
    assert "12" in immutables
    assert any("hypothetical" in item.lower() for item in case["required_qualifications"])
    assert "do not introduce real companies" in case["task"].lower()
