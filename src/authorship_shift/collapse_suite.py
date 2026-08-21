"""Cross-domain collapse experiment and aggregate report.

Runs the same 5 profiles x 2 samples design over every evaluation domain and
aggregates the per-domain collapse statistics into one table and one verdict.

The verdict is the point. A single domain's collapse ratio is a data point; the
question that decides whether to move to LoRA or fine-tuning is whether the
ratio stays near 1.0 *across domains*. This module encodes that decision rule
explicitly rather than leaving it to be eyeballed from five separate reports.

Thresholds are imported from `collapse`, so a per-domain interpretation and the
aggregate verdict can never disagree about what counts as collapsed.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

from .batch_gate import BatchGateConfig, assess_batch
from .candidate_lab import analyze_candidates
from .collapse import (
    COMPOSITE,
    P_SIGNIFICANT,
    RATIO_COLLAPSED,
    RATIO_WEAK,
    STYLISTIC,
    assess_collapse,
)
from .manual_batch import LoadedBatch, load_batch
from .rerank import RerankConfig, rerank

# Per-domain classification keys.
SEPARATED = "separated"
WEAK = "weak"
COLLAPSED = "collapsed"
UNMEASURED = "unmeasured"

# Aggregate verdict keys.
VERDICT_INSUFFICIENT = "insufficient_data"
VERDICT_COLLAPSED = "collapsed_across_domains"
VERDICT_WEAK = "weak_across_domains"
VERDICT_CONTROLLABLE = "controllable"
VERDICT_DOMAIN_DEPENDENT = "domain_dependent"
VERDICT_DAMAGING = "controllable_but_damaging"
VERDICT_GATE_BLOCKED = "gate_blocked"


def _pretty(genre: str | None, case_id: str) -> str:
    if not genre:
        return case_id
    return genre.replace("_", " ").capitalize()


@dataclass
class DomainOutcome:
    case_id: str
    genre: str | None
    display_name: str
    expected_count: int
    candidate_count: int
    complete: bool
    measured: bool
    classification: str
    within_profile_mean: float | None = None
    between_profile_mean: float | None = None
    collapse_ratio: float | None = None
    p_value: float | None = None
    design_has_resolution: bool = False
    significant: bool = False
    composite_ratio: float | None = None
    composite_p_value: float | None = None
    min_nearest_neighbor_distance: float = 0.0
    near_duplicate_pairs: list[tuple[str, str, float]] = field(default_factory=list)
    gate_pass: bool = False
    fidelity_evidence: str = "none"
    gate_failures: list[str] = field(default_factory=list)
    eligible_count: int = 0
    rejected_count: int = 0
    shortlist: list[str] = field(default_factory=list)
    interpretation: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["near_duplicate_pairs"] = [list(pair) for pair in self.near_duplicate_pairs]
        return payload


@dataclass
class SuiteVerdict:
    key: str
    headline: str
    rationale: list[str] = field(default_factory=list)
    next_step: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SuiteReport:
    domains: list[DomainOutcome]
    verdict: SuiteVerdict
    measured_count: int
    incomplete_count: int
    design_note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "domains": [row.to_dict() for row in self.domains],
            "verdict": self.verdict.to_dict(),
            "measured_count": self.measured_count,
            "incomplete_count": self.incomplete_count,
            "design_note": self.design_note,
        }

    def to_markdown(self) -> str:
        return build_markdown(self)


def _classify(outcome: DomainOutcome) -> str:
    if not outcome.measured or outcome.collapse_ratio is None:
        return UNMEASURED
    if outcome.collapse_ratio >= RATIO_WEAK and outcome.significant:
        return SEPARATED
    if outcome.collapse_ratio < RATIO_COLLAPSED:
        return COLLAPSED
    return WEAK


def analyze_domain(
    batch: LoadedBatch,
    *,
    permutations: int = 2000,
    seed: int = 12345,
    select: int = 3,
    gate_config: BatchGateConfig | None = None,
    rerank_config: RerankConfig | None = None,
) -> DomainOutcome:
    """Compute gate, collapse, and rerank results for one domain's batch."""

    outcome = DomainOutcome(
        case_id=batch.case_id,
        genre=batch.genre,
        display_name=_pretty(batch.genre, batch.case_id),
        expected_count=batch.expected_count,
        candidate_count=len(batch.candidates),
        complete=batch.complete,
        measured=False,
        classification=UNMEASURED,
    )

    if not batch.candidates:
        outcome.notes.append("no candidate outputs present")
        return outcome

    analyses = analyze_candidates(batch.manifest["source"], batch.candidates)
    gate = assess_batch(analyses, target_words=batch.target_words, config=gate_config)
    collapse = assess_collapse(batch.labeled, permutations=permutations, seed=seed)
    shortlist = rerank(
        batch.candidates,
        analyses,
        target_words=batch.target_words,
        select=max(1, min(select, len(batch.candidates))),
        config=rerank_config,
    )

    outcome.gate_pass = gate.pass_gate
    outcome.fidelity_evidence = gate.fidelity_evidence
    outcome.gate_failures = list(gate.hard_failures)
    outcome.min_nearest_neighbor_distance = gate.min_nearest_neighbor_distance
    outcome.near_duplicate_pairs = list(collapse.duplicate_pairs)
    outcome.eligible_count = shortlist.eligible_count
    outcome.rejected_count = shortlist.rejected_count
    outcome.shortlist = list(shortlist.selected)
    outcome.notes.extend(collapse.notes)

    by_mode = {row.distance_mode: row for row in collapse.separations}
    stylistic = by_mode.get(STYLISTIC)
    composite = by_mode.get(COMPOSITE)

    if stylistic is not None:
        outcome.measured = True
        outcome.within_profile_mean = stylistic.within_profile_mean
        outcome.between_profile_mean = stylistic.between_profile_mean
        outcome.collapse_ratio = stylistic.separation_ratio
        outcome.p_value = stylistic.p_value
        outcome.design_has_resolution = stylistic.design_has_resolution
        outcome.significant = bool(
            stylistic.design_has_resolution
            and stylistic.p_value is not None
            and stylistic.p_value <= P_SIGNIFICANT
        )
        outcome.interpretation = stylistic.interpretation
    if composite is not None:
        outcome.composite_ratio = composite.separation_ratio
        outcome.composite_p_value = composite.p_value

    outcome.classification = _classify(outcome)
    return outcome


def decide(domains: Sequence[DomainOutcome]) -> SuiteVerdict:
    """Turn per-domain outcomes into the decision this experiment exists to make."""

    measured = [row for row in domains if row.measured]
    rationale: list[str] = []

    if not measured:
        return SuiteVerdict(
            key=VERDICT_INSUFFICIENT,
            headline="Not enough completed generations to decide anything.",
            rationale=[
                f"{len(domains)} domain(s) inspected, none with measurable "
                "within-profile dispersion.",
                "Each domain needs at least two samples for at least one profile.",
            ],
            next_step="Complete the 5 x 5 x 2 generation matrix, then re-run the report.",
        )

    separated = [row for row in measured if row.classification == SEPARATED]
    weak = [row for row in measured if row.classification == WEAK]
    collapsed = [row for row in measured if row.classification == COLLAPSED]

    rationale.append(
        f"{len(measured)} domain(s) measured: {len(separated)} separated, "
        f"{len(weak)} weak, {len(collapsed)} collapsed."
    )

    underpowered = [row for row in measured if not row.design_has_resolution]
    if underpowered:
        rationale.append(
            f"{len(underpowered)} domain(s) lack permutation resolution; their "
            "p-values are floor-bound and cannot show significance."
        )

    duplicates = [row for row in measured if row.near_duplicate_pairs]
    if duplicates:
        rationale.append(
            f"{len(duplicates)} domain(s) contain near-duplicate candidate pairs that "
            "an aggregate mean distance would have hidden: "
            + ", ".join(row.display_name for row in duplicates)
            + "."
        )

    failing = [row for row in measured if not row.gate_pass]
    if failing:
        rationale.append(
            f"{len(failing)} domain(s) failed the fidelity/length gate: "
            + ", ".join(row.display_name for row in failing)
            + "."
        )

    vacuous = [row for row in measured if row.fidelity_evidence == "vacuous"]
    if vacuous:
        rationale.append(
            f"{len(vacuous)} domain(s) have no checkable literal details, so their "
            "fidelity result carries no evidence: "
            + ", ".join(row.display_name for row in vacuous)
            + "."
        )

    # A collapse ratio computed over candidates that lost content or missed the
    # target length says nothing about controllability. Recommending a training
    # programme off such a batch would be the worst outcome this suite can
    # produce, so no verdict is issued until something passes the gate.
    if not any(row.gate_pass for row in measured):
        return SuiteVerdict(
            key=VERDICT_GATE_BLOCKED,
            headline=(
                "Every measured domain failed the fidelity or length gate, so no "
                "collapse conclusion is trustworthy yet."
            ),
            rationale=rationale
            + [
                "The observed ratios may be artifacts of candidates that dropped "
                "content or missed the target length, not evidence about the model's "
                "writing distribution.",
            ],
            next_step=(
                "Fix the fidelity and length failures and re-run. Do not read these "
                "ratios as evidence for or against tuning."
            ),
        )

    # A profile effect bought at the cost of fidelity or writing quality is not a
    # win, so this outranks the ordinary separated verdict.
    if separated and all(not row.gate_pass for row in separated):
        return SuiteVerdict(
            key=VERDICT_DAMAGING,
            headline=(
                "Profiles steer the distribution, but every domain where they do "
                "fails the fidelity or quality gate."
            ),
            rationale=rationale,
            next_step=(
                "Do not read this as controllability. Fix the fidelity and length "
                "failures first, then re-run; the effect may be an artifact of "
                "candidates that dropped content or missed the target length."
            ),
        )

    if not separated and not weak:
        return SuiteVerdict(
            key=VERDICT_COLLAPSED,
            headline=(
                "Collapsed across every measured domain: profile directives move "
                "candidates no further than resampling the same profile does."
            ),
            rationale=rationale,
            next_step=(
                "Prompt- and sampling-level control has reached its limit. The next "
                "research direction is an open-weight model with LoRA or fine-tuning."
            ),
        )

    if not separated:
        return SuiteVerdict(
            key=VERDICT_WEAK,
            headline=(
                "Weak across domains: dispersion leans toward the profiles but no "
                "domain reaches significance."
            ),
            rationale=rationale,
            next_step=(
                "Increase samples per profile before deciding. If the ratio stays "
                "below the separation threshold with a powered design, treat this as "
                "collapse and move to LoRA or fine-tuning."
            ),
        )

    if len(separated) == len(measured):
        return SuiteVerdict(
            key=VERDICT_CONTROLLABLE,
            headline=(
                "Profiles genuinely steer the distribution in every measured domain."
            ),
            rationale=rationale,
            next_step=(
                "Improve generation and reranking before training anything. Tuning is "
                "not yet justified by the evidence."
            ),
        )

    resistant = [row for row in measured if row.classification != SEPARATED]
    return SuiteVerdict(
        key=VERDICT_DOMAIN_DEPENDENT,
        headline=(
            "Domain-dependent controllability: profiles steer some genres and not "
            "others."
        ),
        rationale=rationale
        + [
            "Controllable: " + ", ".join(row.display_name for row in separated) + ".",
            "Resistant: " + ", ".join(row.display_name for row in resistant) + ".",
        ],
        next_step=(
            "Keep prompt-level control for the controllable genres and scope any "
            "tuning work to the resistant ones. A tuned model may only be needed for "
            "part of the corpus."
        ),
    )


def run_suite(
    batch_dirs: Sequence[str | Path],
    *,
    permutations: int = 2000,
    seed: int = 12345,
    select: int = 3,
) -> SuiteReport:
    """Analyze every prepared domain batch and aggregate the result."""

    if not batch_dirs:
        raise ValueError("run_suite requires at least one batch directory")

    outcomes = [
        analyze_domain(
            load_batch(path),
            permutations=permutations,
            seed=seed,
            select=select,
        )
        for path in batch_dirs
    ]
    measured = [row for row in outcomes if row.measured]
    incomplete = [row for row in outcomes if not row.complete]

    design_note = ""
    if measured and all(row.design_has_resolution for row in measured):
        design_note = (
            "All measured domains have adequate permutation resolution."
        )
    elif measured:
        design_note = (
            "Some measured domains are underpowered; their p-values are floor-bound. "
            "Five profiles at two samples is the minimum adequately powered design."
        )

    return SuiteReport(
        domains=outcomes,
        verdict=decide(outcomes),
        measured_count=len(measured),
        incomplete_count=len(incomplete),
        design_note=design_note,
    )


def _num(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def build_markdown(report: SuiteReport) -> str:
    lines = [
        "# Cross-domain collapse experiment",
        "",
        "Design: 5 domains x 5 generation profiles x 2 independent samples per "
        "profile = 50 generations.",
        "",
        "## Verdict",
        "",
        f"**{report.verdict.headline}**",
        "",
    ]
    for item in report.verdict.rationale:
        lines.append(f"- {item}")
    lines.extend(["", f"**Next step.** {report.verdict.next_step}", ""])
    if report.design_note:
        lines.extend([f"_{report.design_note}_", ""])

    lines.extend(
        [
            "## Summary",
            "",
            "| Domain | Collapse ratio | p | Gate | Interpretation |",
            "| --- | ---: | ---: | --- | --- |",
        ]
    )
    for row in report.domains:
        if not row.measured:
            gate = "—"
            interpretation = (
                f"not measured ({row.candidate_count}/{row.expected_count} outputs)"
            )
        else:
            gate = "pass" if row.gate_pass else "FAIL"
            interpretation = row.interpretation or row.classification
        lines.append(
            f"| {row.display_name} | {_num(row.collapse_ratio)} | "
            f"{_num(row.p_value, 4)} | {gate} | {interpretation} |"
        )

    lines.extend(
        [
            "",
            "## Detail",
            "",
            "| Domain | Within | Between | Ratio | p | Powered | Nearest neighbour | "
            "Fidelity evidence | Eligible | Shortlist |",
            "| --- | ---: | ---: | ---: | ---: | --- | ---: | --- | ---: | --- |",
        ]
    )
    for row in report.domains:
        powered = "yes" if row.design_has_resolution else "no" if row.measured else "—"
        shortlist = ", ".join(row.shortlist) if row.shortlist else "—"
        eligible = (
            f"{row.eligible_count}/{row.candidate_count}" if row.candidate_count else "—"
        )
        lines.append(
            f"| {row.display_name} | {_num(row.within_profile_mean, 4)} | "
            f"{_num(row.between_profile_mean, 4)} | {_num(row.collapse_ratio)} | "
            f"{_num(row.p_value, 4)} | {powered} | "
            f"{row.min_nearest_neighbor_distance:.3f} | {row.fidelity_evidence} | "
            f"{eligible} | {shortlist} |"
        )

    flagged = [row for row in report.domains if row.near_duplicate_pairs or row.gate_failures]
    if flagged:
        lines.extend(["", "## Flags", ""])
        for row in flagged:
            lines.append(f"**{row.display_name}**")
            for pair in row.near_duplicate_pairs:
                lines.append(
                    f"- near-duplicate: `{pair[0]}` ~ `{pair[1]}` at distance {pair[2]:.3f}"
                )
            for failure in row.gate_failures:
                lines.append(f"- gate: {failure}")
            lines.append("")

    lines.extend(
        [
            "",
            "## Scope",
            "",
            "These are deterministic local diagnostics. They do not identify human or "
            "AI authorship and are not a surrogate for any commercial detector. "
            "External detector observations, where recorded, are secondary validation "
            "and are never the optimization objective.",
            "",
        ]
    )
    return "\n".join(lines)
