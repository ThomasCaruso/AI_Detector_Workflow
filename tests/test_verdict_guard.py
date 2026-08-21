from authorship_shift.collapse_suite import (
    COLLAPSED,
    SEPARATED,
    WEAK,
    VERDICT_COLLAPSED,
    VERDICT_GATE_BLOCKED,
    VERDICT_INSUFFICIENT,
    VERDICT_PROMPT_CEILING,
    VERDICT_WEAK,
    DomainOutcome,
    SuiteReport,
    SuiteVerdict,
)
from authorship_shift.verdict_guard import apply_final_verdict_guard, trusted_domains

# Verdict keys whose next_step actively directs the project to start a new
# trainable-model intervention. Naming LoRA in order to rule it out is not a
# recommendation, so this invariant is keyed on the verdict itself.
TRAINING_RECOMMENDING_VERDICTS = {VERDICT_COLLAPSED, VERDICT_PROMPT_CEILING}


def _assert_does_not_recommend_training(verdict) -> None:
    assert verdict.key not in TRAINING_RECOMMENDING_VERDICTS


def _domain(
    name: str,
    *,
    classification: str = COLLAPSED,
    complete: bool = True,
    measured: bool = True,
    gate_pass: bool = True,
    fidelity: str = "checked",
    ratio: float = 1.0,
    significant: bool = False,
    candidate_count: int = 10,
    powered: bool = True,
) -> DomainOutcome:
    return DomainOutcome(
        case_id=name,
        genre=name,
        display_name=name,
        expected_count=candidate_count,
        candidate_count=candidate_count if complete else min(4, candidate_count),
        complete=complete,
        measured=measured,
        classification=classification,
        collapse_ratio=ratio if measured else None,
        p_value=0.001 if significant else 0.4,
        design_has_resolution=powered,
        significant=significant,
        gate_pass=gate_pass,
        fidelity_evidence=fidelity,
    )


def _report(domains: list[DomainOutcome]) -> SuiteReport:
    return SuiteReport(
        domains=domains,
        verdict=SuiteVerdict(key="provisional", headline="provisional"),
        measured_count=sum(1 for row in domains if row.measured),
        incomplete_count=sum(1 for row in domains if not row.complete),
    )


def test_partial_suite_can_never_recommend_training():
    report = _report(
        [
            _domain("business"),
            _domain("technical", complete=False, measured=False),
            _domain("science", complete=False, measured=False),
            _domain("professional", complete=False, measured=False),
            _domain("argument", complete=False, measured=False),
        ]
    )

    guarded = apply_final_verdict_guard(report)
    assert guarded.verdict.key == VERDICT_INSUFFICIENT
    _assert_does_not_recommend_training(guarded.verdict)
    assert "remaining independent generations" in guarded.verdict.next_step
    assert "Do not move to LoRA or fine-tuning from a partial suite" in guarded.verdict.next_step


def test_vacuous_and_gate_failing_domains_do_not_vote():
    report = _report(
        [
            _domain("business", gate_pass=True, fidelity="checked"),
            _domain("technical", gate_pass=False, fidelity="checked"),
            _domain("science", gate_pass=True, fidelity="vacuous"),
            _domain("professional", gate_pass=True, fidelity="checked"),
            _domain("argument", gate_pass=False, fidelity="vacuous"),
        ]
    )

    assert [row.case_id for row in trusted_domains(report)] == ["business", "professional"]
    guarded = apply_final_verdict_guard(report)
    assert guarded.verdict.key == VERDICT_GATE_BLOCKED
    _assert_does_not_recommend_training(guarded.verdict)


def test_final_verdict_uses_only_trusted_cross_domain_evidence():
    report = _report(
        [
            _domain("business", classification=COLLAPSED, gate_pass=True),
            _domain("technical", classification=COLLAPSED, gate_pass=True),
            _domain("science", classification=COLLAPSED, gate_pass=True),
            _domain(
                "professional",
                classification=SEPARATED,
                ratio=2.5,
                significant=True,
                gate_pass=False,
            ),
            _domain("argument", gate_pass=True, fidelity="vacuous"),
        ]
    )

    guarded = apply_final_verdict_guard(report)
    assert guarded.verdict.key == VERDICT_COLLAPSED
    assert "3/5 trusted domains" in " ".join(guarded.verdict.rationale)


def test_complete_5x4_study_below_practical_threshold_earns_prompt_ceiling():
    """The final experiment should not ask for endless prompt-only replication."""

    report = _report(
        [
            _domain("technical", classification=COLLAPSED, ratio=0.973, candidate_count=20),
            _domain("argument", classification=WEAK, ratio=1.113, candidate_count=20, significant=True),
            _domain("business", classification=WEAK, ratio=1.120, candidate_count=20),
            # A gate-failing fifth domain is reported but does not vote.
            _domain("professional", classification=WEAK, ratio=1.213, candidate_count=20, gate_pass=False),
            _domain("science", classification=WEAK, ratio=1.227, candidate_count=20, significant=True),
        ]
    )

    guarded = apply_final_verdict_guard(report)
    assert guarded.verdict.key == VERDICT_PROMPT_CEILING
    assert "0.973–1.227" in " ".join(guarded.verdict.rationale)
    assert "mean 1.108" in " ".join(guarded.verdict.rationale)
    assert "open-weight adapter" in guarded.verdict.next_step


def test_practically_large_ratio_blocks_ceiling_even_if_not_significant():
    report = _report(
        [
            _domain("technical", classification=COLLAPSED, ratio=0.98, candidate_count=20),
            _domain("argument", classification=WEAK, ratio=1.12, candidate_count=20),
            _domain("business", classification=WEAK, ratio=1.18, candidate_count=20),
            # Deliberately classify this as weak/not-significant. Magnitude alone
            # should prevent the final guard from declaring a ceiling.
            _domain("science", classification=WEAK, ratio=1.26, candidate_count=20),
            _domain("professional", classification=WEAK, ratio=1.10, candidate_count=20, gate_pass=False),
        ]
    )

    guarded = apply_final_verdict_guard(report)
    assert guarded.verdict.key == VERDICT_WEAK
    _assert_does_not_recommend_training(guarded.verdict)


def test_5x2_depth_is_not_enough_for_practical_ceiling_rule():
    report = _report(
        [
            _domain("a", classification=WEAK, ratio=1.10, candidate_count=10),
            _domain("b", classification=WEAK, ratio=1.11, candidate_count=10),
            _domain("c", classification=WEAK, ratio=1.12, candidate_count=10),
            _domain("d", classification=WEAK, ratio=1.13, candidate_count=10),
            _domain("e", classification=WEAK, ratio=1.14, candidate_count=10),
        ]
    )

    guarded = apply_final_verdict_guard(report)
    assert guarded.verdict.key == VERDICT_WEAK
    _assert_does_not_recommend_training(guarded.verdict)
