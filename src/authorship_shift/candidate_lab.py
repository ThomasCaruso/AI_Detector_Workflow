from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import math
import re
from typing import Iterable, Sequence

from .diversity import pair_distance
from .metrics import measure, sentences, words

NUMBER_RE = re.compile(
    r"(?<!\w)(?:[$€£])?\d+(?:,\d{3})*(?:\.\d+)?%?(?:x|ms|s|m|h|kg|g|km|mi)?(?!\w)",
    re.IGNORECASE,
)
CAPITALIZED_PHRASE_RE = re.compile(
    r"\b(?:[A-Z][A-Za-z0-9&.-]+(?:\s+[A-Z][A-Za-z0-9&.-]+){0,3})\b"
)

GENERIC_SENTENCE_STARTS = {
    "additionally",
    "also",
    "consequently",
    "furthermore",
    "however",
    "moreover",
    "nevertheless",
    "nonetheless",
    "overall",
    "similarly",
    "therefore",
    "ultimately",
}


def _ngrams(tokens: Sequence[str], n: int) -> set[tuple[str, ...]]:
    if len(tokens) < n:
        return set()
    return {tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)}


def _jaccard(a: set[tuple[str, ...]], b: set[tuple[str, ...]]) -> float:
    if not a and not b:
        return 1.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def source_ngram_overlap(source: str, candidate: str, n: int = 3) -> float:
    """Measure literal n-gram overlap with the source.

    This is a rewrite-distance diagnostic, not an authorship or detector score.
    """
    return _jaccard(_ngrams(words(source), n), _ngrams(words(candidate), n))


def sentence_openings(text: str, width: int = 2) -> list[str]:
    openings: list[str] = []
    for sentence in sentences(text):
        toks = words(sentence)
        if toks:
            openings.append(" ".join(toks[:width]))
    return openings


def opening_repeat_ratio(text: str, width: int = 1) -> float:
    openings = sentence_openings(text, width)
    if len(openings) < 2:
        return 0.0
    counts = Counter(openings)
    repeated = sum(count - 1 for count in counts.values() if count > 1)
    return repeated / len(openings)


def opening_entropy(text: str, width: int = 1) -> float:
    openings = sentence_openings(text, width)
    if len(openings) < 2:
        return 0.0
    counts = Counter(openings)
    total = len(openings)
    entropy = -sum((count / total) * math.log2(count / total) for count in counts.values())
    max_entropy = math.log2(total)
    return entropy / max_entropy if max_entropy else 0.0


def generic_sentence_start_ratio(text: str) -> float:
    sents = sentences(text)
    if not sents:
        return 0.0
    hits = 0
    for sentence in sents:
        toks = words(sentence)
        first = toks[0] if toks else ""
        if first in GENERIC_SENTENCE_STARTS:
            hits += 1
    return hits / len(sents)


def extract_immutables(source: str) -> list[str]:
    """Extract conservative surface forms worth checking exactly.

    This is intentionally a precheck, not a semantic-fidelity judge. To avoid
    false positives from ordinary sentence-initial capitalization, it tracks
    numbers, multiword capitalized names, and all-caps identifiers. Single-word
    title-case names should come from the semantic/content lock in a full run.
    """

    items = set(NUMBER_RE.findall(source))
    for phrase in CAPITALIZED_PHRASE_RE.findall(source):
        parts = phrase.split()
        if len(parts) >= 2:
            items.add(phrase)
        elif phrase.isupper() and len(phrase) > 1:
            items.add(phrase)
    return sorted(items, key=lambda value: (value.lower(), value))


def immutable_coverage(source: str, candidate: str) -> tuple[float, list[str]]:
    items = extract_immutables(source)
    if not items:
        return 1.0, []
    missing = [item for item in items if item not in candidate]
    return (len(items) - len(missing)) / len(items), missing


@dataclass
class CandidateAnalysis:
    candidate_id: str
    word_count: int
    sentence_count: int
    sentence_length_cv: float
    lexical_diversity: float
    transition_start_ratio: float
    generic_sentence_start_ratio: float
    opening_repeat_ratio: float
    opening_entropy: float
    repeated_trigram_ratio: float
    source_trigram_overlap: float
    structural_distance_from_source: float
    immutable_coverage: float
    missing_immutables: list[str]
    mean_pairwise_distance: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def analyze_candidate(source: str, candidate_id: str, text: str) -> CandidateAnalysis:
    metrics = measure(text)
    coverage, missing = immutable_coverage(source, text)
    from .metrics import structural_distance

    return CandidateAnalysis(
        candidate_id=candidate_id,
        word_count=metrics.word_count,
        sentence_count=metrics.sentence_count,
        sentence_length_cv=metrics.sentence_length_cv,
        lexical_diversity=metrics.lexical_diversity,
        transition_start_ratio=metrics.transition_start_ratio,
        generic_sentence_start_ratio=generic_sentence_start_ratio(text),
        opening_repeat_ratio=opening_repeat_ratio(text),
        opening_entropy=opening_entropy(text),
        repeated_trigram_ratio=metrics.repeated_trigram_ratio,
        source_trigram_overlap=source_ngram_overlap(source, text, 3),
        structural_distance_from_source=structural_distance(source, text),
        immutable_coverage=coverage,
        missing_immutables=missing,
    )


def analyze_candidates(
    source: str,
    candidates: Iterable[tuple[str, str]],
) -> list[CandidateAnalysis]:
    candidate_list = [(cid, text) for cid, text in candidates]
    analyses = [analyze_candidate(source, cid, text) for cid, text in candidate_list]
    text_by_id = dict(candidate_list)

    for analysis in analyses:
        other_ids = [
            other.candidate_id
            for other in analyses
            if other.candidate_id != analysis.candidate_id
        ]
        if other_ids:
            analysis.mean_pairwise_distance = sum(
                pair_distance(
                    text_by_id[analysis.candidate_id],
                    text_by_id[other_id],
                )
                for other_id in other_ids
            ) / len(other_ids)
    return analyses
