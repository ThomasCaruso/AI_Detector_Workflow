from __future__ import annotations

from dataclasses import dataclass, asdict
from itertools import combinations
from typing import Any

from .metrics import structural_distance, words


def lexical_jaccard(a: str, b: str) -> float:
    sa, sb = set(words(a)), set(words(b))
    if not sa and not sb:
        return 1.0
    union = sa | sb
    return len(sa & sb) / len(union) if union else 1.0


def pair_distance(a: str, b: str) -> float:
    """Composite diversity descriptor; it is not a detector surrogate."""
    lexical_distance = 1.0 - lexical_jaccard(a, b)
    structure = structural_distance(a, b)
    return 0.55 * lexical_distance + 0.45 * structure


@dataclass
class DiversitySummary:
    candidate_count: int
    pair_count: int
    mean_pair_distance: float
    min_pair_distance: float
    max_pair_distance: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_diversity(texts: list[str]) -> DiversitySummary:
    distances = [pair_distance(a, b) for a, b in combinations(texts, 2)]
    if not distances:
        return DiversitySummary(len(texts), 0, 0.0, 0.0, 0.0)
    return DiversitySummary(
        candidate_count=len(texts),
        pair_count=len(distances),
        mean_pair_distance=round(sum(distances) / len(distances), 4),
        min_pair_distance=round(min(distances), 4),
        max_pair_distance=round(max(distances), 4),
    )
