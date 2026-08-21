"""Tests for the cross-domain collapse suite.

The verdict function is what decides whether the project moves to LoRA, so each
documented interpretation rule is pinned to a fixture here.
"""

import json

import pytest

from authorship_shift.collapse_suite import (
    COLLAPSED,
    SEPARATED,
    UNMEASURED,
    VERDICT_COLLAPSED,
    VERDICT_CONTROLLABLE,
    VERDICT_DAMAGING,
    VERDICT_DOMAIN_DEPENDENT,
    VERDICT_GATE_BLOCKED,
    VERDICT_INSUFFICIENT,
    VERDICT_WEAK,
    WEAK,
    DomainOutcome,
    analyze_domain,
    build_markdown,
    decide,
    run_suite,
)
from authorship_shift.manual_batch import load_batch, prepare_batch
from test_engine_pipeline import ATOMS, CANDIDATES, SOURCE


def _outcome(
    case_id: str,
    *,
    ratio: float | None = 1.0,
    significant: bool = False,
    gate_pass: bool = True,
    measured: bool = True,
    powered: bool = True,
    fidelity: str = "checked",
    duplicates: list | None = None,
) -> DomainOutcome:
    outcome = DomainOutcome(
        case_id=case_id,
        genre=case_id,
        display_name=case_id.replace("_", " ").capitalize(),
        expected_count=10,
        candidate_count=10 if measured else 0,
        complete=measured,
        measured=measured,
        classification=UNMEASURED,
        collapse_ratio=ratio if measured else None,
        p_value=0.001 if significant else 0.400,
        design_has_resolution=powered,
        significant=significant,
        gate_pass=gate_pass,
        fidelity_evidence=fidelity,
        near_duplicate_pairs=duplicates or [],
    )
    if not measured or ratio is None:
        outcome.classification = UNMEASURED
    elif ratio >= 1.25 and significant:
        outcome.classification = SEPARATED
    elif ratio < 1.05:
        outcome.classification = COLLAPSED
    else:
        outcome.classification = WEAK
    return outcome


# --- verdict rules -------------------------------------------------------


def test_no_measured_domains_decides_nothing():
    verdict = decide([_outcome("a", measured=False), _outcome("b", measured=False)])
    assert verdict.key == VERDICT_INSUFFICIENT
    assert "Complete the 5 x 5 x 2" in verdict.next_step


def test_ratio_near_one_across_domains_points_at_lora():
    """Rule 1: the base model dominates, so tuning is the next direction."""

    domains = [_outcome(f"d{i}", ratio=1.01) for i in range(5)]
    verdict = decide(domains)
    assert verdict.key == VERDICT_COLLAPSED
    assert "LoRA" in verdict.next_step or "fine-tuning" in verdict.next_step


def test_consistent_significant_separation_says_improve_first():
    """Rule 2: profiles genuinely steer, so do not train anything yet."""

    domains = [_outcome(f"d{i}", ratio=1.9, significant=True) for i in range(5)]
    verdict = decide(domains)
    assert verdict.key == VERDICT_CONTROLLABLE
    assert "before training" in verdict.next_step


def test_mixed_domains_report_domain_dependent_controllability():
    """Rule 3: tuning may only be needed for the resistant genres."""

    domains = [
        _outcome("business", ratio=2.0, significant=True),
        _outcome("technical", ratio=1.8, significant=True),
        _outcome("science", ratio=1.00),
        _outcome("legal", ratio=1.02),
    ]
    verdict = decide(domains)
    assert verdict.key == VERDICT_DOMAIN_DEPENDENT
    rationale = " ".join(verdict.rationale)
    assert "Controllable:" in rationale
    assert "Resistant:" in rationale
    assert "Science" in rationale


def test_separation_bought_with_broken_fidelity_is_not_a_win():
    """Rule 4: high ratio plus gate failures must not read as controllability."""

    domains = [
        _outcome("business", ratio=2.4, significant=True, gate_pass=False),
        _outcome("technical", ratio=2.1, significant=True, gate_pass=False),
        # At least one clean domain, otherwise the gate-blocked rule fires first.
        _outcome("science", ratio=1.01, gate_pass=True),
    ]
    verdict = decide(domains)
    assert verdict.key == VERDICT_DAMAGING
    assert "Do not read this as controllability" in verdict.next_step


def test_collapse_over_gate_failing_domains_blocks_the_verdict():
    """A ratio from broken candidates must never recommend a training programme."""

    domains = [_outcome(f"d{i}", ratio=0.7, gate_pass=False) for i in range(3)]
    verdict = decide(domains)
    assert verdict.key == VERDICT_GATE_BLOCKED
    assert "LoRA" not in verdict.next_step
    assert "Fix the fidelity and length failures" in verdict.next_step


def test_one_passing_domain_is_enough_to_reach_a_conclusion():
    domains = [
        _outcome("business", ratio=1.01, gate_pass=True),
        _outcome("technical", ratio=1.01, gate_pass=False),
    ]
    verdict = decide(domains)
    assert verdict.key == VERDICT_COLLAPSED


def test_near_duplicate_pairs_are_surfaced_in_the_rationale():
    """Rule 5: a collapse an aggregate mean would have hidden."""

    domains = [
        _outcome("business", ratio=1.02, duplicates=[("p1-c1", "p3-c2", 0.01)]),
        _outcome("technical", ratio=1.01),
    ]
    verdict = decide(domains)
    assert any("near-duplicate" in line for line in verdict.rationale)
    assert any("Business" in line for line in verdict.rationale)


def test_weak_but_insignificant_effect_asks_for_more_samples():
    domains = [_outcome(f"d{i}", ratio=1.15) for i in range(4)]
    verdict = decide(domains)
    assert verdict.key == VERDICT_WEAK
    assert "Increase samples per profile" in verdict.next_step


def test_underpowered_domains_are_called_out():
    domains = [_outcome(f"d{i}", ratio=1.01, powered=False) for i in range(3)]
    verdict = decide(domains)
    assert any("permutation resolution" in line for line in verdict.rationale)


def test_vacuous_fidelity_is_called_out():
    domains = [_outcome("argument", ratio=1.01, fidelity="vacuous")]
    verdict = decide(domains)
    assert any("no checkable literal details" in line for line in verdict.rationale)


# --- end to end ----------------------------------------------------------


CASE = {
    "id": "pipeline_case_001",
    "genre": "technical_explanation",
    "target_words": len(CANDIDATES[0].split()),
    "source": SOURCE,
    "task": "Explain the revenue result.",
    "required_qualifications": ATOMS,
}


def _prepared(tmp_path, *, fill: bool = True):
    batch_dir = tmp_path / CASE["id"]
    manifest = prepare_batch(CASE, batch_dir, samples_per_profile=2)
    if fill:
        for entry, text in zip(manifest["candidates"], CANDIDATES):
            (batch_dir / entry["expected_output_file"]).write_text(text, encoding="utf-8")
    return batch_dir


def test_analyze_domain_produces_a_measured_outcome(tmp_path):
    outcome = analyze_domain(load_batch(_prepared(tmp_path)), permutations=200)

    assert outcome.measured is True
    assert outcome.complete is True
    assert outcome.candidate_count == 10
    assert outcome.expected_count == 10
    assert outcome.display_name == "Technical explanation"
    assert outcome.design_has_resolution is True
    assert outcome.collapse_ratio is not None
    assert outcome.composite_ratio is not None
    assert outcome.fidelity_evidence == "checked"


def test_analyze_domain_handles_an_unfilled_batch(tmp_path):
    outcome = analyze_domain(load_batch(_prepared(tmp_path, fill=False)))

    assert outcome.measured is False
    assert outcome.complete is False
    assert outcome.candidate_count == 0
    assert outcome.classification == UNMEASURED


def test_run_suite_aggregates_and_renders(tmp_path):
    _prepared(tmp_path)
    report = run_suite([tmp_path / CASE["id"]], permutations=200)

    assert report.measured_count == 1
    assert report.incomplete_count == 0
    assert "adequate permutation resolution" in report.design_note

    markdown = report.to_markdown()
    assert "| Domain | Collapse ratio | p | Gate | Interpretation |" in markdown
    assert "Technical explanation" in markdown
    assert "## Verdict" in markdown
    assert "5 domains x 5 generation profiles x 2 independent samples" in markdown

    payload = json.loads(json.dumps(report.to_dict()))
    assert payload["domains"][0]["case_id"] == CASE["id"]
    assert payload["verdict"]["key"]


def test_run_suite_requires_a_batch():
    with pytest.raises(ValueError, match="at least one batch"):
        run_suite([])


def test_markdown_renders_unmeasured_domains_without_crashing(tmp_path):
    _prepared(tmp_path, fill=False)
    report = run_suite([tmp_path / CASE["id"]])
    markdown = build_markdown(report)

    assert "not measured (0/10 outputs)" in markdown
    assert "—" in markdown
