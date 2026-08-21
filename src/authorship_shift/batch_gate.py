from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Sequence

from .candidate_lab import CandidateAnalysis


@dataclass(frozen=True)
class BatchGateConfig:
    min_candidates: int = 3
    min_mean_pairwise_distance: float = 0.10
    min_immutable_coverage: float = 1.0
    target_word_tolerance: float = 0.20
    warn_opening_repeat_ratio: float = 0.30
    warn_transition_start_ratio: float = 0.25
    warn_source_trigram_overlap: float = 0.45
    # A pair closer than this is treated as a near-duplicate. Mean pairwise
    # distance cannot see two collapsed candidates inside a spread batch.
    min_nearest_neighbor_distance: float = 0.05
    # Report cases where the literal-detail precheck had nothing to check, so a
    # vacuous coverage of 1.0 is never read as verified fidelity.
    warn_on_vacuous_immutables: bool = True


@dataclass
class BatchGateReport:
    pass_gate: bool
    hard_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    candidate_failures: dict[str, list[str]] = field(default_factory=dict)
    candidate_warnings: dict[str, list[str]] = field(default_factory=dict)
    mean_pairwise_distance: float = 0.0
    min_nearest_neighbor_distance: float = 0.0
    fidelity_evidence: str = "none"

    def to_dict(self) -> dict:
        return asdict(self)


def assess_batch(
    analyses: Sequence[CandidateAnalysis],
    *,
    target_words: int | None = None,
    config: BatchGateConfig | None = None,
) -> BatchGateReport:
    """Decide whether a batch is worth deeper manual or external review.

    This gate checks reproducibility/fidelity prerequisites and obvious profile
    collapse. It does not predict human authorship and does not rank candidates
    by a commercial detector objective.
    """

    cfg = config or BatchGateConfig()
    hard_failures: list[str] = []
    warnings: list[str] = []
    candidate_failures: dict[str, list[str]] = {}
    candidate_warnings: dict[str, list[str]] = {}

    if len(analyses) < cfg.min_candidates:
        hard_failures.append(
            f"candidate_count={len(analyses)} is below required minimum {cfg.min_candidates}"
        )

    mean_pairwise = (
        sum(row.mean_pairwise_distance for row in analyses) / len(analyses)
        if analyses
        else 0.0
    )
    if analyses and mean_pairwise < cfg.min_mean_pairwise_distance:
        hard_failures.append(
            "candidate batch appears collapsed: "
            f"mean_pairwise_distance={mean_pairwise:.3f} < {cfg.min_mean_pairwise_distance:.3f}"
        )

    neighbor_distances = [
        row.nearest_neighbor_distance for row in analyses if row.nearest_neighbor_id is not None
    ]
    min_neighbor = min(neighbor_distances) if neighbor_distances else 0.0
    if neighbor_distances and min_neighbor < cfg.min_nearest_neighbor_distance:
        duplicates = sorted(
            f"{row.candidate_id}~{row.nearest_neighbor_id}"
            for row in analyses
            if row.nearest_neighbor_id is not None
            and row.nearest_neighbor_distance < cfg.min_nearest_neighbor_distance
        )
        hard_failures.append(
            "near-duplicate candidates: "
            f"min_nearest_neighbor_distance={min_neighbor:.3f} < "
            f"{cfg.min_nearest_neighbor_distance:.3f}; pairs={duplicates}"
        )

    # A batch whose source exposes no literal details cannot supply fidelity
    # evidence from this precheck, however high its coverage number looks.
    checkable = [row.immutable_count for row in analyses]
    if not analyses:
        fidelity_evidence = "none"
    elif all(count == 0 for count in checkable):
        fidelity_evidence = "vacuous"
    elif any(count == 0 for count in checkable):
        fidelity_evidence = "partial"
    else:
        fidelity_evidence = "checked"

    if cfg.warn_on_vacuous_immutables and fidelity_evidence in {"vacuous", "partial"}:
        warnings.append(
            f"immutable-detail precheck is {fidelity_evidence}: "
            "coverage=1.0 reflects nothing to check, not verified fidelity"
        )

    for row in analyses:
        failures: list[str] = []
        row_warnings: list[str] = []

        if row.immutable_coverage < cfg.min_immutable_coverage:
            failures.append(
                f"immutable_coverage={row.immutable_coverage:.3f}; "
                f"missing={row.missing_immutables}"
            )

        if target_words is not None and target_words > 0:
            lower = target_words * (1.0 - cfg.target_word_tolerance)
            upper = target_words * (1.0 + cfg.target_word_tolerance)
            if not (lower <= row.word_count <= upper):
                failures.append(
                    f"word_count={row.word_count} outside target range "
                    f"[{lower:.0f}, {upper:.0f}]"
                )

        if row.opening_repeat_ratio > cfg.warn_opening_repeat_ratio:
            row_warnings.append(
                f"opening_repeat_ratio={row.opening_repeat_ratio:.3f}"
            )
        if row.transition_start_ratio > cfg.warn_transition_start_ratio:
            row_warnings.append(
                f"transition_start_ratio={row.transition_start_ratio:.3f}"
            )
        if row.source_trigram_overlap > cfg.warn_source_trigram_overlap:
            row_warnings.append(
                f"source_trigram_overlap={row.source_trigram_overlap:.3f}"
            )

        if failures:
            candidate_failures[row.candidate_id] = failures
        if row_warnings:
            candidate_warnings[row.candidate_id] = row_warnings

    if candidate_failures:
        hard_failures.append(
            f"{len(candidate_failures)} candidate(s) failed fidelity/length prerequisites"
        )
    if candidate_warnings:
        warnings.append(
            f"{len(candidate_warnings)} candidate(s) triggered style-distance warnings"
        )

    return BatchGateReport(
        pass_gate=not hard_failures,
        hard_failures=hard_failures,
        warnings=warnings,
        candidate_failures=candidate_failures,
        candidate_warnings=candidate_warnings,
        mean_pairwise_distance=mean_pairwise,
        min_nearest_neighbor_distance=min_neighbor,
        fidelity_evidence=fidelity_evidence,
    )
