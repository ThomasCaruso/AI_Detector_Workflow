from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict
import math
import re

WORD_RE = re.compile(r"\b[\w'-]+\b", re.UNICODE)
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])")

TRANSITION_STARTS = {
    "additionally", "furthermore", "moreover", "however", "therefore",
    "consequently", "nevertheless", "nonetheless", "ultimately",
    "overall", "indeed", "similarly", "conversely", "meanwhile",
    "firstly", "secondly", "finally", "in conclusion", "in summary",
}


def words(text: str) -> list[str]:
    return [m.group(0).lower() for m in WORD_RE.finditer(text)]


def sentences(text: str) -> list[str]:
    parts = [s.strip() for s in SENTENCE_RE.split(text.strip()) if s.strip()]
    return parts if parts else ([text.strip()] if text.strip() else [])


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]


def _mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _cv(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    mean = _mean(xs)
    if mean == 0:
        return 0.0
    variance = sum((x - mean) ** 2 for x in xs) / len(xs)
    return math.sqrt(variance) / mean


def repeated_ngram_ratio(tokens: list[str], n: int = 3) -> float:
    if len(tokens) < n:
        return 0.0
    grams = [tuple(tokens[i:i+n]) for i in range(len(tokens)-n+1)]
    counts = Counter(grams)
    repeated = sum(c - 1 for c in counts.values() if c > 1)
    return repeated / len(grams)


def transition_start_ratio(sents: list[str]) -> float:
    if not sents:
        return 0.0
    hits = 0
    for s in sents:
        lower = s.lower().lstrip('"\'“‘')
        if any(lower.startswith(t) for t in TRANSITION_STARTS):
            hits += 1
    return hits / len(sents)


@dataclass
class TextMetrics:
    word_count: int
    sentence_count: int
    paragraph_count: int
    lexical_diversity: float
    sentence_length_mean: float
    sentence_length_cv: float
    paragraph_length_mean: float
    paragraph_length_cv: float
    short_sentence_ratio: float
    long_sentence_ratio: float
    repeated_trigram_ratio: float
    transition_start_ratio: float
    semicolons_per_1k_words: float
    em_dashes_per_1k_words: float

    def to_dict(self):
        return asdict(self)


def measure(text: str) -> TextMetrics:
    toks = words(text)
    sents = sentences(text)
    paras = paragraphs(text)
    sent_lengths = [len(words(s)) for s in sents]
    para_lengths = [len(words(p)) for p in paras]
    wc = len(toks)
    scale = 1000 / wc if wc else 0.0
    return TextMetrics(
        word_count=wc,
        sentence_count=len(sents),
        paragraph_count=len(paras),
        lexical_diversity=(len(set(toks)) / wc) if wc else 0.0,
        sentence_length_mean=_mean(sent_lengths),
        sentence_length_cv=_cv(sent_lengths),
        paragraph_length_mean=_mean(para_lengths),
        paragraph_length_cv=_cv(para_lengths),
        short_sentence_ratio=(sum(1 for x in sent_lengths if x <= 8) / len(sent_lengths)) if sent_lengths else 0.0,
        long_sentence_ratio=(sum(1 for x in sent_lengths if x >= 30) / len(sent_lengths)) if sent_lengths else 0.0,
        repeated_trigram_ratio=repeated_ngram_ratio(toks, 3),
        transition_start_ratio=transition_start_ratio(sents),
        semicolons_per_1k_words=text.count(";") * scale,
        em_dashes_per_1k_words=text.count("—") * scale,
    )


def structural_distance(a: str, b: str) -> float:
    """A non-detector surrogate measuring structural difference between two texts.

    This intentionally does not claim to predict any commercial detector.
    """
    ma, mb = measure(a), measure(b)
    fields = [
        "sentence_length_mean", "sentence_length_cv", "paragraph_length_mean",
        "paragraph_length_cv", "short_sentence_ratio", "long_sentence_ratio",
        "repeated_trigram_ratio", "transition_start_ratio",
        "semicolons_per_1k_words", "em_dashes_per_1k_words",
    ]
    vals = []
    for f in fields:
        x, y = float(getattr(ma, f)), float(getattr(mb, f))
        denom = max(abs(x), abs(y), 1e-6)
        vals.append(min(abs(x-y)/denom, 1.0))
    return sum(vals) / len(vals)
