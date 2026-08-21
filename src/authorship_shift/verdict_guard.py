"""Safety policy for cross-domain training-direction decisions.

The collapse suite intentionally supports partial reporting, but a partial report
must not accidentally become a model-training recommendation. This module keeps
progress reporting separate from the expensive decision the experiment exists to
inform.
"""

from __future__ import annotations

from .collapse_suite import (
    VERDICT_GATE_BLOCKED,
    VERDICT_INSUFFICIENT,
    SuiteReport,
    SuiteVerdict,
    decide,
)

# Five seed domains are used by the central experiment. Requiring three checked,
# gate-passing domains gives the final verdict a cross-domain majority while
# still allowing one or two domains to fail for reasons that need separate work.
MIN_TRUSTED_DOMAINS = 3


def trusted_domains(report: SuiteReport):
    """Domains allowed to influence a training-direction verdict.

    A domain must be complete, measurable, pass the batch gate, and have actual
    literal fidelity evidence. Vacuous immutable coverage is useful metadata but
    is not verification and therefore does not get a vote in a LoRA decision.
    """

    return [
        row
        for row in report.domains
        if row.complete
        and row.measured
        and row.gate_pass
        and row.fidelity_evidence == "checked"
    ]


def apply_final_verdict_guard(
    report: SuiteReport,
    *,
    minimum_trusted_domains: int = MIN_TRUSTED_DOMAINS,
) -> SuiteReport:
    """Replace provisional verdicts that are unsafe to act on.

    Per-domain statistics remain available throughout the run. The guard only
    controls the aggregate action recommendation.
    """

    if report.incomplete_count:
        complete = len(report.domains) - report.incomplete_count
        report.verdict = SuiteVerdict(
            key=VERDICT_INSUFFICIENT,
            headline=(
                "Cross-domain suite is incomplete, so the current collapse statistics "
                "are provisional and cannot justify a training decision."
            ),
            rationale=[
                f"{complete}/{len(report.domains)} domains are complete.",
                "Partial domain statistics are still useful for catching fidelity, "
                "length, or profile-collapse problems before generating the rest.",
            ],
            next_step=(
                "Complete the remaining independent generations, then re-run the report. "
                "Do not move to LoRA or fine-tuning from a partial suite."
            ),
        )
        return report

    trusted = trusted_domains(report)
    if len(trusted) < minimum_trusted_domains:
        report.verdict = SuiteVerdict(
            key=VERDICT_GATE_BLOCKED,
            headline=(
                "Too few trustworthy domains remain for a cross-domain training decision."
            ),
            rationale=[
                f"{len(trusted)}/{len(report.domains)} domains are complete, gate-passing, "
                "and backed by checked immutable-detail evidence.",
                "Gate-failing, unmeasured, partial-evidence, and vacuous-evidence domains "
                "are reported but excluded from the training-direction vote.",
            ],
            next_step=(
                "Repair the failed fidelity or length cases until at least "
                f"{minimum_trusted_domains} domains provide trustworthy evidence, then "
                "re-run the report."
            ),
        )
        return report

    # Recompute the action verdict using only evidence that survived the guard.
    verdict = decide(trusted)
    excluded = len(report.domains) - len(trusted)
    verdict.rationale.append(
        f"Final action verdict uses {len(trusted)}/{len(report.domains)} trusted domains; "
        f"{excluded} domain(s) are excluded from the vote because their evidence is not "
        "fully checked and gate-passing."
    )
    report.verdict = verdict
    return report
