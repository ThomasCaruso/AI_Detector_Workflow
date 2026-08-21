"""Safety policy for cross-domain training-direction decisions.

The collapse suite intentionally supports partial reporting, but a partial report
must not accidentally become a model-training recommendation. This module keeps
progress reporting separate from the expensive decision the experiment exists to
inform.
"""

from __future__ import annotations

from statistics import mean

from .collapse import RATIO_WEAK
from .collapse_suite import (
    VERDICT_GATE_BLOCKED,
    VERDICT_INSUFFICIENT,
    VERDICT_PROMPT_CEILING,
    SuiteReport,
    SuiteVerdict,
    decide,
)

# Three checked, gate-passing domains remain the minimum for an ordinary
# cross-domain verdict. The stronger practical-ceiling decision below requires
# four trusted domains and the larger 5x4-style replication depth.
MIN_TRUSTED_DOMAINS = 3
MIN_CEILING_DOMAINS = 4
MIN_CANDIDATES_PER_DOMAIN_FOR_CEILING = 20


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


def _prompt_ceiling_is_earned(trusted) -> bool:
    """Return True when more prompt-only sampling is no longer the useful next test.

    The practical threshold is intentionally magnitude-first. A tiny effect can
    be statistically significant with enough samples; that does not make it
    useful. To call the prompt/profile ceiling reached, require:

    - at least four independent trusted domains;
    - at least twenty candidates per domain (the 5 profiles x 4 samples design);
    - adequate permutation resolution in every voting domain; and
    - every voting domain below the predeclared useful-separation ratio of 1.25.

    Any trusted domain at or above 1.25 blocks the ceiling decision even if its
    p-value is not significant, because a practically large but uncertain effect
    deserves replication rather than immediate escalation to model training.
    """

    if len(trusted) < MIN_CEILING_DOMAINS:
        return False
    for row in trusted:
        if row.candidate_count < MIN_CANDIDATES_PER_DOMAIN_FOR_CEILING:
            return False
        if not row.design_has_resolution:
            return False
        if row.collapse_ratio is None or row.collapse_ratio >= RATIO_WEAK:
            return False
    return True


def _ceiling_verdict(trusted, total_domains: int) -> SuiteVerdict:
    ratios = [float(row.collapse_ratio) for row in trusted if row.collapse_ratio is not None]
    names = ", ".join(row.display_name for row in trusted)
    return SuiteVerdict(
        key=VERDICT_PROMPT_CEILING,
        headline=(
            "Prompt/profile control has reached a measured practical ceiling across "
            "the trusted domains."
        ),
        rationale=[
            (
                f"{len(trusted)}/{total_domains} domains are complete, gate-passing, "
                "and backed by checked fidelity evidence."
            ),
            (
                f"Trusted collapse ratios span {min(ratios):.3f}–{max(ratios):.3f} "
                f"with mean {mean(ratios):.3f}; none reaches the predeclared "
                f"useful-separation threshold of {RATIO_WEAK:.2f}."
            ),
            (
                "Each voting domain uses at least twenty candidates and adequate "
                "permutation resolution, so additional prompt-only samples would "
                "mainly estimate the same weak effect more precisely."
            ),
            "Trusted domains: " + names + ".",
        ],
        next_step=(
            "Freeze the prompt/profile experiment and proceed to the open-weight "
            "adapter research phase. Compare a frozen base model against a LoRA/QLoRA "
            "adapter under the same fidelity and held-out evaluation contract."
        ),
    )


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

    if _prompt_ceiling_is_earned(trusted):
        report.verdict = _ceiling_verdict(trusted, len(report.domains))
        return report

    # Recompute the ordinary action verdict using only evidence that survived the guard.
    verdict = decide(trusted)
    excluded = len(report.domains) - len(trusted)
    verdict.rationale.append(
        f"Final action verdict uses {len(trusted)}/{len(report.domains)} trusted domains; "
        f"{excluded} domain(s) are excluded from the vote because their evidence is not "
        "fully checked and gate-passing."
    )
    report.verdict = verdict
    return report
