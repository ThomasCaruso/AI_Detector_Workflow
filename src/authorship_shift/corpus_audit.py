from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from itertools import combinations
import re
from typing import Iterable

from .lora_data import LoraExample

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")


@dataclass(frozen=True)
class NearDuplicatePair:
    left_id: str
    right_id: str
    left_split: str
    right_split: str
    similarity: float


@dataclass
class CorpusAuditReport:
    example_count: int
    word_count: int
    examples_by_genre: dict[str, int]
    words_by_genre: dict[str, int]
    examples_by_provenance: dict[str, int]
    words_by_provenance: dict[str, int]
    examples_by_source: dict[str, int]
    words_by_source: dict[str, int]
    largest_source_example_share: float
    largest_source_word_share: float
    near_duplicates: list[NearDuplicatePair] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["near_duplicates"] = [asdict(pair) for pair in self.near_duplicates]
        return payload


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text)]


def _shingles(text: str, n: int = 5) -> set[tuple[str, ...]]:
    tokens = _tokens(text)
    if len(tokens) < n:
        return {tuple(tokens)} if tokens else set()
    return {tuple(tokens[index : index + n]) for index in range(len(tokens) - n + 1)}


def _jaccard(left: set[tuple[str, ...]], right: set[tuple[str, ...]]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def audit_corpus(
    examples: Iterable[LoraExample],
    *,
    near_duplicate_threshold: float = 0.80,
    max_source_share: float = 0.15,
    min_genre_examples: int = 5,
) -> CorpusAuditReport:
    rows = list(examples)
    examples_by_genre: Counter[str] = Counter()
    words_by_genre: Counter[str] = Counter()
    examples_by_provenance: Counter[str] = Counter()
    words_by_provenance: Counter[str] = Counter()
    examples_by_source: Counter[str] = Counter()
    words_by_source: Counter[str] = Counter()

    total_words = 0
    for row in rows:
        words = row.word_count
        total_words += words
        examples_by_genre[row.genre] += 1
        words_by_genre[row.genre] += words
        examples_by_provenance[row.provenance.kind] += 1
        words_by_provenance[row.provenance.kind] += words
        examples_by_source[row.provenance.source_id] += 1
        words_by_source[row.provenance.source_id] += words

    example_total = len(rows)
    largest_example_share = (
        max(examples_by_source.values(), default=0) / example_total if example_total else 0.0
    )
    largest_word_share = (
        max(words_by_source.values(), default=0) / total_words if total_words else 0.0
    )

    shingles = {row.id: _shingles(row.target_text) for row in rows}
    near_duplicates: list[NearDuplicatePair] = []
    for left, right in combinations(rows, 2):
        similarity = _jaccard(shingles[left.id], shingles[right.id])
        if similarity >= near_duplicate_threshold:
            near_duplicates.append(
                NearDuplicatePair(
                    left_id=left.id,
                    right_id=right.id,
                    left_split=left.split,
                    right_split=right.split,
                    similarity=similarity,
                )
            )

    warnings: list[str] = []
    if largest_example_share > max_source_share:
        warnings.append(
            f"largest source contributes {largest_example_share:.1%} of examples, above "
            f"configured maximum {max_source_share:.1%}"
        )
    if largest_word_share > max_source_share:
        warnings.append(
            f"largest source contributes {largest_word_share:.1%} of words, above "
            f"configured maximum {max_source_share:.1%}"
        )

    for genre, count in sorted(examples_by_genre.items()):
        if count < min_genre_examples:
            warnings.append(
                f"genre {genre!r} has only {count} example(s), below target minimum {min_genre_examples}"
            )

    cross_split = [pair for pair in near_duplicates if pair.left_split != pair.right_split]
    if cross_split:
        warnings.append(
            f"{len(cross_split)} near-duplicate pair(s) cross train/dev/holdout boundaries"
        )
    elif near_duplicates:
        warnings.append(
            f"{len(near_duplicates)} near-duplicate target pair(s) found within splits"
        )

    return CorpusAuditReport(
        example_count=example_total,
        word_count=total_words,
        examples_by_genre=dict(sorted(examples_by_genre.items())),
        words_by_genre=dict(sorted(words_by_genre.items())),
        examples_by_provenance=dict(sorted(examples_by_provenance.items())),
        words_by_provenance=dict(sorted(words_by_provenance.items())),
        examples_by_source=dict(sorted(examples_by_source.items())),
        words_by_source=dict(sorted(words_by_source.items())),
        largest_source_example_share=largest_example_share,
        largest_source_word_share=largest_word_share,
        near_duplicates=near_duplicates,
        warnings=warnings,
    )
