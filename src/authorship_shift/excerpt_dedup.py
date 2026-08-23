from __future__ import annotations

from dataclasses import asdict, dataclass
from itertools import combinations
import re
from typing import Iterable

from .corpus_pipeline import RawExcerpt

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


@dataclass(frozen=True)
class ExcerptDuplicatePair:
    left_id: str
    right_id: str
    left_source_id: str
    right_source_id: str
    similarity: float
    kind: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExcerptDedupReport:
    exact_duplicates: tuple[ExcerptDuplicatePair, ...]
    cross_source_near_duplicates: tuple[ExcerptDuplicatePair, ...]
    within_source_near_duplicates: tuple[ExcerptDuplicatePair, ...]
    near_duplicate_threshold: float

    @property
    def valid(self) -> bool:
        return not self.exact_duplicates and not self.cross_source_near_duplicates

    def to_dict(self) -> dict:
        return {
            "valid": self.valid,
            "near_duplicate_threshold": self.near_duplicate_threshold,
            "exact_duplicates": [row.to_dict() for row in self.exact_duplicates],
            "cross_source_near_duplicates": [
                row.to_dict() for row in self.cross_source_near_duplicates
            ],
            "within_source_near_duplicates": [
                row.to_dict() for row in self.within_source_near_duplicates
            ],
        }


def _normalized_exact(text: str) -> str:
    return " ".join(text.split())


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text)]


def _shingles(text: str, n: int = 5) -> set[tuple[str, ...]]:
    tokens = _tokens(text)
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {
        tuple(tokens[index : index + n])
        for index in range(len(tokens) - n + 1)
    }


def _jaccard(left: set[tuple[str, ...]], right: set[tuple[str, ...]]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def audit_raw_excerpt_duplicates(
    excerpts: Iterable[RawExcerpt],
    *,
    near_duplicate_threshold: float = 0.80,
) -> ExcerptDedupReport:
    """Reject duplicate training targets before annotation packets are frozen.

    Exact duplicates are always invalid after whitespace normalization. Near
    duplicates across different source documents are also invalid because source-
    level split assignment can place them on opposite sides of train/dev/holdout.
    Near duplicates within one source are reported for review but are not fatal:
    every excerpt from that source receives the same split, and adjacent legitimate
    passages can intentionally share context.
    """

    if not (0.0 < near_duplicate_threshold <= 1.0):
        raise ValueError("near_duplicate_threshold must be in (0, 1]")

    rows = list(excerpts)
    exact = {row.id: _normalized_exact(row.target_text) for row in rows}
    shingles = {row.id: _shingles(row.target_text) for row in rows}

    exact_duplicates: list[ExcerptDuplicatePair] = []
    cross_source_near: list[ExcerptDuplicatePair] = []
    within_source_near: list[ExcerptDuplicatePair] = []

    for left, right in combinations(rows, 2):
        if exact[left.id] == exact[right.id]:
            exact_duplicates.append(
                ExcerptDuplicatePair(
                    left_id=left.id,
                    right_id=right.id,
                    left_source_id=left.source_id,
                    right_source_id=right.source_id,
                    similarity=1.0,
                    kind="exact",
                )
            )
            continue

        similarity = _jaccard(shingles[left.id], shingles[right.id])
        if similarity < near_duplicate_threshold:
            continue
        pair = ExcerptDuplicatePair(
            left_id=left.id,
            right_id=right.id,
            left_source_id=left.source_id,
            right_source_id=right.source_id,
            similarity=similarity,
            kind="near",
        )
        if left.source_id == right.source_id:
            within_source_near.append(pair)
        else:
            cross_source_near.append(pair)

    return ExcerptDedupReport(
        exact_duplicates=tuple(exact_duplicates),
        cross_source_near_duplicates=tuple(cross_source_near),
        within_source_near_duplicates=tuple(within_source_near),
        near_duplicate_threshold=near_duplicate_threshold,
    )
