from authorship_shift.collapse_suite import (
    COLLAPSED,
    SEPARATED,
    VERDICT_COLLAPSED,
    VERDICT_GATE_BLOCKED,
    VERDICT_INSUFFICIENT,
    DomainOutcome,
    SuiteReport,
    SuiteVerdict,
)
from authorship_shift.verdict_guard import apply_final_verdict_guard, trusted_domains


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
) -> DomainOutcome:
    return DomainOutcome(
        case_id=name,
        genre=name,
        display_name=name,
        expected_count=10,
        candidate_count=10 if complete else 4,
        complete=complete,
        measured=measured,
        classification=classification,
        collapse_ratio=ratio if measured else None,
        p_value=0.001 if significant else 0.4,
        design_has_resolution=True,
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
    assert "LoRA" not in guarded.verdict.next_step
    assert "remaining independent generations" in guarded.verdict.next_step


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
    assert "LoRA" not in guarded.verdict.next_step


def test_final_verdict_uses_only_trusted_cross_domain_evidence():
    report = _report(
        [
            _domain("business", classification=COLLAPSED, gate_pass=True),
            _domain("technical", classification=COLLAPSED, gate_pass=True),
            _domain("science", classification=COLLAPSED, gate_pass=True),
            # A large apparent profile effect that failed fidelity must not vote.
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
