"""Deterministic reranking over candidates that clear the batch gate.

`docs/ENGINE_V2.md` sets out the intended selection sequence: drop candidates
that lose immutable details, drop candidates that are clearly worse writing,
then prefer useful diversity over near-duplicates. It is equally explicit that
the diagnostics are not quality targets - a high structural distance is not
automatically good, a low transition ratio is not automatically good, and
lexical diversity is not a proxy for quality.

This module therefore scores **defects**, never merit. Every term penalizes a
value for crossing a threshold in the bad direction and contributes nothing
otherwise, so no candidate can win by pushing a metric to an extreme. A text
with ordinary transition use scores the same zero as one with no transitions at
all.

Two stages the deterministic layer cannot perform are left to a judge model or a
human: verifying that causal direction and certainty survived, and scoring voice
match against genuine writing samples. Selection here is a shortlist for that
review, not a verdict.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Sequence

from .candidate_lab import CandidateAnalysis
from .diversity import pair_distance


@dataclass(frozen=True)
class DefectRule:
    """One penalty term.

    ``direction`` is ``"above"`` when large values are the defect and
    ``"below"`` when small values are. ``scale`` is the distance past the
    threshold at which the penalty saturates at 1.0.
    """

    metric: str
    direction: str
    threshold: float
    scale: float
    weight: float
    description: str


DEFAULT_RULES: tuple[DefectRule, ...] = (
    DefectRule(
        "transition_start_ratio", "above", 0.15, 0.25, 1.0,
        "sentences stacked behind connectives",
    ),
    DefectRule(
        "generic_sentence_start_ratio", "above", 0.20, 0.30, 0.8,
        "openings drawn from a small generic set",
    ),
    DefectRule(
        "opening_repeat_ratio", "above", 0.15, 0.35, 1.0,
        "the same sentence opening reused",
    ),
    DefectRule(
        "opening_entropy", "below", 0.75, 0.35, 0.8,
        "monotonous distribution of sentence openings",
    ),
    DefectRule(
        "repeated_trigram_ratio", "above", 0.02, 0.08, 0.8,
        "phrases repeating within the candidate",
    ),
    DefectRule(
        "source_trigram_overlap", "above", 0.35, 0.35, 1.2,
        "literal wording carried over from the source",
    ),
    DefectRule(
        "sentence_length_cv", "below", 0.25, 0.25, 0.6,
        "uniform sentence lengths with little rhythm",
    ),
)


@dataclass(frozen=True)
class RerankConfig:
    min_immutable_coverage: float = 1.0
    target_word_tolerance: float = 0.20
    # A candidate within this much of the best defect score is treated as
    # quality-equivalent, so diversity may decide between them but never
    # override a real quality gap.
    quality_tolerance: float = 0.15
    rules: tuple[DefectRule, ...] = DEFAULT_RULES


@dataclass
class CandidateScore:
    candidate_id: str
    eligible: bool
    defect_score: float
    defects: list[str] = field(default_factory=list)
    rejections: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RerankResult:
    ranked: list[CandidateScore]
    selected: list[str]
    eligible_count: int
    rejected_count: int
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ranked": [row.to_dict() for row in self.ranked],
            "selected": list(self.selected),
            "eligible_count": self.eligible_count,
            "rejected_count": self.rejected_count,
            "notes": list(self.notes),
        }


def _penalty(value: float, rule: DefectRule) -> float:
    if rule.direction == "above":
        excess = value - rule.threshold
    elif rule.direction == "below":
        excess = rule.threshold - value
    else:  # pragma: no cover - guarded by construction
        raise ValueError(f"unknown direction {rule.direction!r}")
    if excess <= 0:
        return 0.0
    return min(excess / rule.scale, 1.0)


def score_candidate(
    analysis: CandidateAnalysis,
    *,
    target_words: int | None = None,
    config: RerankConfig | None = None,
) -> CandidateScore:
    """Score one candidate by accumulated defects. Lower is better."""

    cfg = config or RerankConfig()
    rejections: list[str] = []

    if analysis.immutable_coverage < cfg.min_immutable_coverage:
        rejections.append(
            f"immutable_coverage={analysis.immutable_coverage:.3f}; "
            f"missing={analysis.missing_immutables}"
        )
    if target_words is not None and target_words > 0:
        lower = target_words * (1.0 - cfg.target_word_tolerance)
        upper = target_words * (1.0 + cfg.target_word_tolerance)
        if not (lower <= analysis.word_count <= upper):
            rejections.append(
                f"word_count={analysis.word_count} outside [{lower:.0f}, {upper:.0f}]"
            )

    total = 0.0
    weight_sum = 0.0
    defects: list[str] = []
    for rule in cfg.rules:
        value = float(getattr(analysis, rule.metric))
        penalty = _penalty(value, rule)
        weight_sum += rule.weight
        total += penalty * rule.weight
        if penalty > 0:
            defects.append(f"{rule.metric}={value:.3f} ({rule.description})")

    return CandidateScore(
        candidate_id=analysis.candidate_id,
        eligible=not rejections,
        defect_score=total / weight_sum if weight_sum else 0.0,
        defects=defects,
        rejections=rejections,
    )


def rerank(
    candidates: Sequence[tuple[str, str]],
    analyses: Sequence[CandidateAnalysis],
    *,
    target_words: int | None = None,
    select: int = 3,
    config: RerankConfig | None = None,
) -> RerankResult:
    """Rank candidates by defect score and shortlist a diverse subset.

    ``candidates`` is a sequence of ``(candidate_id, text)``. Selection is
    greedy: the cleanest candidate is taken first, then each further slot goes to
    whichever quality-equivalent candidate sits furthest from everything already
    chosen. Diversity breaks ties; it never outranks quality.
    """

    if select < 1:
        raise ValueError("select must be >= 1")

    cfg = config or RerankConfig()
    text_by_id = dict(candidates)
    missing = [row.candidate_id for row in analyses if row.candidate_id not in text_by_id]
    if missing:
        raise ValueError(f"no text supplied for candidate(s): {sorted(missing)}")

    scores = [
        score_candidate(row, target_words=target_words, config=cfg) for row in analyses
    ]
    # Stable, deterministic ordering: cleanest first, candidate id breaks ties.
    scores.sort(key=lambda row: (row.defect_score, row.candidate_id))

    eligible = [row for row in scores if row.eligible]
    notes: list[str] = []
    if not eligible:
        notes.append(
            "no candidate satisfied the fidelity and length prerequisites; "
            "nothing was shortlisted"
        )
        return RerankResult(
            ranked=scores,
            selected=[],
            eligible_count=0,
            rejected_count=len(scores),
            notes=notes,
        )

    selected: list[str] = [eligible[0].candidate_id]
    remaining = [row for row in eligible[1:]]
    while remaining and len(selected) < select:
        best_defect = min(row.defect_score for row in remaining)
        pool = [
            row for row in remaining
            if row.defect_score <= best_defect + cfg.quality_tolerance
        ]
        # Among quality-equivalent candidates, take the one furthest from the
        # shortlist so the result is not three phrasings of one construction.
        pick = max(
            pool,
            key=lambda row: (
                min(
                    pair_distance(text_by_id[row.candidate_id], text_by_id[chosen])
                    for chosen in selected
                ),
                -row.defect_score,
                row.candidate_id,
            ),
        )
        selected.append(pick.candidate_id)
        remaining = [row for row in remaining if row.candidate_id != pick.candidate_id]

    if len(selected) < select:
        notes.append(
            f"requested {select} candidates but only {len(selected)} were eligible"
        )
    notes.append(
        "deterministic shortlist only: causal/certainty fidelity and voice match "
        "still require a judge model or human review"
    )

    return RerankResult(
        ranked=scores,
        selected=selected,
        eligible_count=len(eligible),
        rejected_count=len(scores) - len(eligible),
        notes=notes,
    )
