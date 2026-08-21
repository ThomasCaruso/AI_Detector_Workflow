from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from itertools import combinations
import re
from typing import Iterable

from .lora_data import LoraExample

_TOKEN_RE = re.compile(r"[A-Za-z0-9']+")
_TARGET_SPLITS = ("train", "dev", "holdout")


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
    examples_by_split: dict[str, int]
    examples_by_genre_split: dict[str, dict[str, int]]
    sources_by_genre_split: dict[str, dict[str, int]]
    missing_genre_splits: list[str]
    genre_split_coverage_ok: bool
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


def genre_split_coverage(
    examples: Iterable[LoraExample],
    *,
    expected_genres: Iterable[str] | None = None,
) -> tuple[dict[str, dict[str, int]], dict[str, dict[str, int]], list[str]]:
    """Return example/source matrices and every missing genre x split cell."""

    rows = list(examples)
    observed_genres = {row.genre for row in rows}
    genres = sorted(
        set(str(genre).strip() for genre in (expected_genres or observed_genres) if str(genre).strip())
        | observed_genres
    )
    example_matrix = {
        genre: {split: 0 for split in _TARGET_SPLITS}
        for genre in genres
    }
    source_sets: dict[str, dict[str, set[str]]] = {
        genre: {split: set() for split in _TARGET_SPLITS}
        for genre in genres
    }

    for row in rows:
        if row.split not in _TARGET_SPLITS:
            continue
        example_matrix[row.genre][row.split] += 1
        source_sets[row.genre][row.split].add(row.provenance.source_id)

    source_matrix = {
        genre: {
            split: len(source_sets[genre][split])
            for split in _TARGET_SPLITS
        }
        for genre in genres
    }
    missing = [
        f"{genre}:{split}"
        for genre in genres
        for split in _TARGET_SPLITS
        if example_matrix[genre][split] == 0
    ]
    return example_matrix, source_matrix, missing


def audit_corpus(
    examples: Iterable[LoraExample],
    *,
    near_duplicate_threshold: float = 0.80,
    max_source_share: float = 0.15,
    min_genre_examples: int = 5,
    expected_genres: Iterable[str] | None = None,
) -> CorpusAuditReport:
    rows = list(examples)
    examples_by_genre: Counter[str] = Counter()
    words_by_genre: Counter[str] = Counter()
    examples_by_split: Counter[str] = Counter()
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
        examples_by_split[row.split] += 1
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

    example_matrix, source_matrix, missing_genre_splits = genre_split_coverage(
        rows,
        expected_genres=expected_genres,
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

    if missing_genre_splits:
        warnings.append(
            "genre x split coverage is incomplete: " + ", ".join(missing_genre_splits)
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
        examples_by_split={split: examples_by_split.get(split, 0) for split in _TARGET_SPLITS},
        examples_by_genre_split=example_matrix,
        sources_by_genre_split=source_matrix,
        missing_genre_splits=missing_genre_splits,
        genre_split_coverage_ok=not missing_genre_splits,
        examples_by_provenance=dict(sorted(examples_by_provenance.items())),
        words_by_provenance=dict(sorted(words_by_provenance.items())),
        examples_by_source=dict(sorted(examples_by_source.items())),
        words_by_source=dict(sorted(words_by_source.items())),
        largest_source_example_share=largest_example_share,
        largest_source_word_share=largest_word_share,
        near_duplicates=near_duplicates,
        warnings=warnings,
    )
