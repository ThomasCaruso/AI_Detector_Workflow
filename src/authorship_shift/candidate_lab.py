from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
import math
import re
from typing import Iterable, Sequence

from .added_detail import added_name_hits
from .diversity import pair_distance
from .metrics import measure, sentences, words

NUMBER_RE = re.compile(
    r"(?<!\w)(?:[$€£])?\d+(?:,\d{3})*(?:\.\d+)?%?(?:x|ms|s|m|h|kg|g|km|mi)?(?!\w)",
    re.IGNORECASE,
)
# A capitalized token may contain an internal dot ("U.S.A"-style) but must not
# end with one. Allowing a trailing dot lets a phrase run across a sentence
# boundary and produce impossible immutables such as "EBITDA. Normalized EBITDA",
# which no faithful rewrite can ever contain.
_CAP_TOKEN = r"[A-Z][A-Za-z0-9&-]+(?:\.[A-Z][A-Za-z0-9&-]+)*"
CAPITALIZED_PHRASE_RE = re.compile(
    rf"\b(?:{_CAP_TOKEN}(?:\s+{_CAP_TOKEN}){{0,3}})\b"
)
_LEADING_ARTICLES = {"A", "An", "The"}

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

_SMALL_NUMBER_WORDS = {
    0: "zero",
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
    11: "eleven",
    12: "twelve",
    13: "thirteen",
    14: "fourteen",
    15: "fifteen",
    16: "sixteen",
    17: "seventeen",
    18: "eighteen",
    19: "nineteen",
}
_TENS_WORDS = {
    20: "twenty",
    30: "thirty",
    40: "forty",
    50: "fifty",
    60: "sixty",
    70: "seventy",
    80: "eighty",
    90: "ninety",
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


def _phrase_has_case_variant(source: str, phrase: str) -> bool:
    """Return True when ``phrase`` also appears with ordinary lowercase casing.

    Sentence-initial common-noun phrases can look like proper names to a purely
    capitalization-based extractor. If the same words occur elsewhere in the
    source with different casing, the source itself supplies evidence that the
    phrase is ordinary terminology rather than an immutable name. This keeps
    real names such as ``Northstar Mobility`` while dropping phrases such as
    ``Normalized EBITDA`` when ``normalized EBITDA`` also appears in the source.
    """

    flexible = re.escape(phrase).replace(r"\ ", r"\s+")
    pattern = re.compile(
        r"(?<![0-9A-Za-z_])" + flexible + r"(?![0-9A-Za-z_])",
        re.IGNORECASE,
    )
    canonical = " ".join(phrase.split())
    return any(" ".join(match.group(0).split()) != canonical for match in pattern.finditer(source))


def extract_immutables(source: str) -> list[str]:
    """Extract conservative surface forms worth checking exactly.

    This is intentionally a precheck, not a semantic-fidelity judge. To avoid
    false positives from ordinary sentence-initial capitalization, it tracks
    numbers, multiword capitalized names, and all-caps identifiers. A multiword
    capitalized phrase is excluded when the same words appear elsewhere in the
    source with different casing, which is evidence that the phrase is ordinary
    terminology rather than a name. Leading articles are stripped from a likely
    identifier, so ``The Atlas`` protects ``Atlas`` rather than treating the
    sentence article as part of the name. Single-word title-case names otherwise
    remain too ambiguous for this surface precheck and belong in the semantic
    content lock.
    """

    items = set(NUMBER_RE.findall(source))
    for phrase in CAPITALIZED_PHRASE_RE.findall(source):
        parts = phrase.split()
        if len(parts) >= 2 and parts[0] in _LEADING_ARTICLES:
            remainder = " ".join(parts[1:])
            if all(part.isupper() for part in parts[1:]) or not _phrase_has_case_variant(
                source, remainder
            ):
                items.add(remainder)
            continue
        if len(parts) >= 2:
            if all(part.isupper() for part in parts) or not _phrase_has_case_variant(source, phrase):
                items.add(phrase)
        elif phrase.isupper() and len(phrase) > 1:
            items.add(phrase)
    return sorted(items, key=lambda value: (value.lower(), value))


def _immutable_pattern(item: str) -> re.Pattern[str]:
    """Build a boundary-aware matcher for one immutable detail.

    A plain substring test is wrong in both directions. It lets a bare ``9``
    match inside ``1,900``, ``2029``, or ``9.1x``, and it rejects a candidate
    that writes ``normalized EBITDA`` mid-sentence when the source happened to
    capitalize the phrase at a sentence start.
    """

    left = r"(?<![0-9A-Za-z_])"
    right = r"(?![0-9A-Za-z_])"
    if item[0].isdigit():
        # Do not match the tail of a longer number: "9" inside "1,900".
        left += r"(?<![.,$€£])"
    if item[-1].isdigit():
        # Do not match the head of a longer number: "2.0" inside "2.05".
        right += r"(?![.,]\d)"
    return re.compile(left + re.escape(item) + right, re.IGNORECASE)


def _integer_word_body(value: int) -> str | None:
    """Return a regex body for an integer's ordinary English word form."""

    if value in _SMALL_NUMBER_WORDS:
        return re.escape(_SMALL_NUMBER_WORDS[value])
    if value in _TENS_WORDS:
        return re.escape(_TENS_WORDS[value])
    if 20 < value < 100:
        tens = (value // 10) * 10
        ones = value % 10
        return re.escape(_TENS_WORDS[tens]) + r"(?:-|\s+)" + re.escape(_SMALL_NUMBER_WORDS[ones])
    return None


def _integer_word_pattern(item: str) -> re.Pattern[str] | None:
    """Return a conservative word-form matcher for a bare integer immutable.

    Only unsigned bare integers from 0 through 99 are normalized. Currency,
    decimals, multipliers, dates with punctuation, and units remain exact-surface
    checks. Percentages have their own narrow equivalence rule below. Compound
    values accept either ``twenty-one`` or ``twenty one``.
    """

    if not re.fullmatch(r"\d{1,2}", item):
        return None
    body = _integer_word_body(int(item))
    if body is None:
        return None
    # Treat hyphenated compounds as a single lexical unit so ``nine`` does not
    # accidentally satisfy an immutable inside ``nine-year`` or similar text.
    return re.compile(
        r"(?<![0-9A-Za-z_-])" + body + r"(?![0-9A-Za-z_-])",
        re.IGNORECASE,
    )


def _percentage_word_pattern(item: str) -> re.Pattern[str] | None:
    """Match an integer percentage written with words instead of ``%``.

    The rule is intentionally limited to unsigned integer percentages from 0 to
    99. ``8%`` may match ``8 percent``, ``eight percent``, or ``eight per cent``.
    It does not match ``8 percentage points`` because percent and percentage-point
    changes are not generally interchangeable, and it does not normalize currency,
    decimals, units, or multipliers.
    """

    match = re.fullmatch(r"(\d{1,2})%", item)
    if match is None:
        return None
    value = int(match.group(1))
    word_body = _integer_word_body(value)
    if word_body is None:
        return None
    number_body = re.escape(str(value))
    body = rf"(?:{number_body}|{word_body})\s+(?:percent|per\s+cent)"
    return re.compile(
        r"(?<![0-9A-Za-z_-])" + body + r"(?![0-9A-Za-z_-])",
        re.IGNORECASE,
    )


def immutable_matches(candidate: str, item: str) -> bool:
    if _immutable_pattern(item).search(candidate) is not None:
        return True
    integer_word_pattern = _integer_word_pattern(item)
    if integer_word_pattern is not None and integer_word_pattern.search(candidate) is not None:
        return True
    percentage_word_pattern = _percentage_word_pattern(item)
    return percentage_word_pattern is not None and percentage_word_pattern.search(candidate) is not None


def immutable_coverage(source: str, candidate: str) -> tuple[float, list[str]]:
    """Return literal-detail coverage and the details that went missing.

    Coverage of ``1.0`` with an empty item list means *nothing was checkable*,
    not *fidelity was verified*. Callers that need to tell those apart should
    use :func:`extract_immutables` or read ``CandidateAnalysis.immutable_count``.
    """

    items = extract_immutables(source)
    if not items:
        return 1.0, []
    missing = [item for item in items if not immutable_matches(candidate, item)]
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
    immutable_count: int = 0
    mean_pairwise_distance: float = 0.0
    nearest_neighbor_distance: float = 0.0
    nearest_neighbor_id: str | None = None
    added_name_hits: list[str] = field(default_factory=list)

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
        immutable_count=len(extract_immutables(source)),
        added_name_hits=added_name_hits(source, text),
    )


def analyze_candidates(
    source: str,
    candidates: Iterable[tuple[str, str]],
) -> list[CandidateAnalysis]:
    candidate_list = [(cid, text) for cid, text in candidates]
    analyses = [analyze_candidate(source, cid, text) for cid, text in candidate_list]

    # Compute each pair once. pair_distance is symmetric but not cheap, and the
    # previous implementation evaluated every pair twice.
    count = len(candidate_list)
    matrix: list[list[float]] = [[0.0] * count for _ in range(count)]
    for i in range(count):
        for j in range(i + 1, count):
            distance = pair_distance(candidate_list[i][1], candidate_list[j][1])
            matrix[i][j] = distance
            matrix[j][i] = distance

    for index, analysis in enumerate(analyses):
        others = [(matrix[index][j], candidate_list[j][0]) for j in range(count) if j != index]
        if not others:
            continue
        analysis.mean_pairwise_distance = sum(d for d, _ in others) / len(others)
        # The mean hides near-duplicate pairs inside an otherwise spread batch,
        # so record the closest neighbor explicitly.
        nearest_distance, nearest_id = min(others, key=lambda pair: pair[0])
        analysis.nearest_neighbor_distance = nearest_distance
        analysis.nearest_neighbor_id = nearest_id
    return analyses
