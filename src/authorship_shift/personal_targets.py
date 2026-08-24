"""Target selection, unit grouping, and annotation gates for the personal corpus.

This is the machinery between a deterministic extraction
(:mod:`authorship_shift.personal_extraction`) and a reviewable
semantic-plan -> authentic-target training example:

* :func:`classify_regions` decides which extracted regions may ever be a
  training target;
* :func:`group_target_units` collects adjacent eligible regions into coherent
  rhetorical units;
* :func:`check_plan_fidelity` gates a drafted semantic plan against its target;
* :func:`run_leakage_checks` gates the finished annotation set.

Nothing here approves anything. Every gate reports; a human decides.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Iterable, Mapping, Sequence

from .personal_extraction import Region

# Word budget for one training unit. "Where possible" - a single oversized
# source paragraph is kept whole rather than split mid-paragraph.
DEFAULT_MIN_WORDS = 100
DEFAULT_MAX_WORDS = 300

HEADING_STYLE_PATTERN = re.compile(r"^Heading\d*$|^Title$|^Subtitle$", re.IGNORECASE)

# Structural ineligibility reasons, in the order they are tested.
REASON_NON_BODY = "non_body_part"
REASON_TABLE = "tabular_data"
REASON_HEADING_STYLE = "heading_style"
REASON_BARE_URL = "url_metadata"
REASON_FROZEN_EXCLUSION = "frozen_region_exclusion"
REASON_HOLDOUT = "holdout_document"

# Style instructions that must never reach a semantic plan. The target
# distribution, not the prompt, supplies the personalization signal.
FORBIDDEN_PLAN_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"\bwrite (?:it )?like\b", "instructs imitation of a person's style"),
    (r"\b(?:in|match|mimic|imitate|emulate|replicate|copy)\w*\s+(?:the\s+)?"
     r"(?:author'?s?|writer'?s?|thomas'?s?|his|her|their)\s+"
     r"(?:voice|style|tone|wording|phrasing|diction)\b", "instructs style imitation"),
    (r"\b(?:voice|style|tone) of the (?:author|writer|original)\b", "instructs style imitation"),
    (r"\b(?:sentence|paragraph)s? (?:should|must) (?:be|average|run)\b.*\b\d+",
     "prescribes sentence or paragraph length"),
    (r"\bkeep sentences (?:short|long)\b", "prescribes sentence length"),
    (r"\buse the (?:same|exact) (?:words|wording|phrases|phrasing|vocabulary)\b",
     "instructs vocabulary imitation"),
    (r"\b(?:ai[- ]?detector|detector|gptzero|turnitin|perplexity score|burstiness)\b",
     "references detection"),
    (r"\b(?:human|ai)[- ]?(?:like|sounding)\b", "references detection"),
)

_HEDGE_MARKERS = (
    "although", "though", "however", "but ", "yet ", "while ", "whereas",
    "despite", "unless", "except", "may ", "might ", "could ", "perhaps",
    "not necessarily", "rather than", "instead of", "arguably", "somewhat",
    "at least", "only if", "i think", "i believe", "seems", "tends to",
    "in contrast", "on the other hand", "limitation", "caveat",
)

_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-]*")


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _normalised_words(text: str) -> list[str]:
    return [word.lower().replace("’", "'") for word in _words(text)]


def _ngrams(tokens: Sequence[str], size: int) -> set[tuple[str, ...]]:
    if len(tokens) < size:
        return set()
    return {tuple(tokens[i : i + size]) for i in range(len(tokens) - size + 1)}


# ---------------------------------------------------------------------------
# Region eligibility
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RegionVerdict:
    """Whether one extracted region may serve as a training target."""

    region_id: str
    block_index: int
    words: int
    eligible: bool
    reason: str | None = None
    flags: tuple[str, ...] = ()

    @property
    def ineligible(self) -> bool:
        return not self.eligible


def _is_bare_url(text: str) -> bool:
    stripped = text.strip()
    return stripped.startswith(("http://", "https://", "www.", "doi:")) and " " not in stripped


def classify_regions(
    regions: Sequence[Region],
    *,
    frozen_excluded_block_indices: Iterable[int] = (),
    reviewed_ineligible: Mapping[int, str] | None = None,
    reviewed_flags: Mapping[int, Sequence[str]] | None = None,
    document_is_holdout: bool = False,
) -> tuple[RegionVerdict, ...]:
    """Decide target eligibility for every region of one source, in order.

    Structural rules are applied mechanically. Judgements that need a human
    reading - a byline, an assignment prompt, a citation line, quoted source
    text - come in through ``reviewed_ineligible``, keyed by block index, so the
    authorship review is recorded rather than guessed at by a classifier.

    A holdout document has no eligible regions at all: the split is
    document-level, so no paragraph of it may become a training target.
    """

    frozen = set(frozen_excluded_block_indices)
    reviewed = dict(reviewed_ineligible or {})
    flags = {index: tuple(value) for index, value in (reviewed_flags or {}).items()}

    verdicts: list[RegionVerdict] = []
    for region in regions:
        reason: str | None = None
        if document_is_holdout:
            reason = REASON_HOLDOUT
        elif region.block_index in frozen:
            reason = REASON_FROZEN_EXCLUSION
        elif region.part != "body":
            reason = REASON_NON_BODY
        elif region.in_table:
            reason = REASON_TABLE
        elif region.style and HEADING_STYLE_PATTERN.match(region.style):
            reason = REASON_HEADING_STYLE
        elif _is_bare_url(region.text):
            reason = REASON_BARE_URL
        elif region.block_index in reviewed:
            reason = reviewed[region.block_index]

        verdicts.append(
            RegionVerdict(
                region_id=region.region_id,
                block_index=region.block_index,
                words=region.word_count,
                eligible=reason is None,
                reason=reason,
                flags=flags.get(region.block_index, ()),
            )
        )
    return tuple(verdicts)


# ---------------------------------------------------------------------------
# Unit grouping
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TargetUnit:
    """One coherent rhetorical unit assembled from adjacent eligible regions."""

    source_id: str
    region_ids: tuple[str, ...]
    block_indices: tuple[int, ...]
    target_text: str
    words: int
    flags: tuple[str, ...] = ()
    oversized_single_paragraph: bool = False


def _balanced_partition(sizes: Sequence[int], groups: int) -> list[tuple[int, int]]:
    """Split a contiguous run into ``groups`` parts, minimising the largest part.

    Deterministic: ties resolve to the earliest split point, so the same run
    always partitions the same way.
    """

    count = len(sizes)
    if groups >= count:
        return [(i, i + 1) for i in range(count)]

    prefix = [0]
    for size in sizes:
        prefix.append(prefix[-1] + size)

    # best[g][i] = minimal achievable maximum part when splitting sizes[i:] into g parts.
    infinity = float("inf")
    best = [[infinity] * (count + 1) for _ in range(groups + 1)]
    cut = [[0] * (count + 1) for _ in range(groups + 1)]
    for g in range(groups + 1):
        best[g][count] = 0 if g == 0 else infinity
    for g in range(1, groups + 1):
        for i in range(count - 1, -1, -1):
            for j in range(i + 1, count + 1):
                if best[g - 1][j] == infinity:
                    continue
                part = prefix[j] - prefix[i]
                candidate = max(part, best[g - 1][j])
                if candidate < best[g][i]:
                    best[g][i] = candidate
                    cut[g][i] = j

    spans: list[tuple[int, int]] = []
    index = 0
    for g in range(groups, 0, -1):
        end = cut[g][index]
        spans.append((index, end))
        index = end
    return spans


def group_target_units(
    regions: Sequence[Region],
    verdicts: Sequence[RegionVerdict],
    *,
    source_id: str,
    max_words: int = DEFAULT_MAX_WORDS,
    split_before_block_indices: Iterable[int] = (),
    paragraph_separator: str = "\n\n",
) -> tuple[TargetUnit, ...]:
    """Group adjacent eligible regions into target units.

    An ineligible region - a heading, a citation line, a byline - ends the
    current run, so units never span a structural boundary. ``split_before``
    adds reviewed rhetorical boundaries that no structural signal marks, such as
    an inline "Reflection:" label that starts a new move inside a run.

    Runs longer than ``max_words`` are partitioned at paragraph boundaries only.
    Sentences are never split, and a single paragraph already over budget is
    kept whole and reported rather than cut.
    """

    by_index = {region.block_index: region for region in regions}
    hard_splits = set(split_before_block_indices)

    runs: list[list[RegionVerdict]] = []
    current: list[RegionVerdict] = []
    for verdict in verdicts:
        if verdict.ineligible:
            if current:
                runs.append(current)
                current = []
            continue
        if current and verdict.block_index in hard_splits:
            runs.append(current)
            current = []
        current.append(verdict)
    if current:
        runs.append(current)

    units: list[TargetUnit] = []
    for run in runs:
        sizes = [verdict.words for verdict in run]
        total = sum(sizes)
        groups = 1 if total <= max_words else -(-total // max_words)
        for start, end in _balanced_partition(sizes, groups):
            chunk = run[start:end]
            texts = [by_index[verdict.block_index].text for verdict in chunk]
            words = sum(verdict.words for verdict in chunk)
            flags: list[str] = []
            for verdict in chunk:
                for flag in verdict.flags:
                    if flag not in flags:
                        flags.append(flag)
            units.append(
                TargetUnit(
                    source_id=source_id,
                    region_ids=tuple(verdict.region_id for verdict in chunk),
                    block_indices=tuple(verdict.block_index for verdict in chunk),
                    target_text=paragraph_separator.join(texts),
                    words=words,
                    flags=tuple(flags),
                    oversized_single_paragraph=len(chunk) == 1 and words > max_words,
                )
            )
    return tuple(units)


def unit_length_summary(units: Sequence[TargetUnit]) -> dict[str, float | int]:
    if not units:
        return {"units": 0, "words": 0, "median": 0, "min": 0, "max": 0}
    lengths = sorted(unit.words for unit in units)
    middle = len(lengths) // 2
    median = (
        lengths[middle]
        if len(lengths) % 2
        else (lengths[middle - 1] + lengths[middle]) / 2
    )
    return {
        "units": len(units),
        "words": sum(lengths),
        "median": median,
        "min": lengths[0],
        "max": lengths[-1],
    }


# ---------------------------------------------------------------------------
# Verbatim third-party quotation inside targets
# ---------------------------------------------------------------------------

# Straight and curly double quotes only. Apostrophes are excluded deliberately:
# treating them as delimiters matches across ordinary possessives and produces
# nonsense spans.
_QUOTED_SPAN_RE = re.compile(r"[“\"]([^“”\"]+)[”\"]")

# How a reviewed long quotation inside an eligible target is accounted for.
QUOTATION_SELF = "self_quotation"
QUOTATION_TITLE = "work_title"
QUOTATION_DISPOSITIONS = frozenset({QUOTATION_SELF, QUOTATION_TITLE})


@dataclass(frozen=True)
class QuotationFinding:
    region_id: str
    words: int
    span: str
    disposition: str | None = None

    @property
    def accounted_for(self) -> bool:
        return self.disposition in QUOTATION_DISPOSITIONS


def find_long_quotations(text: str, *, min_words: int = 8) -> tuple[tuple[int, str], ...]:
    """Quoted spans of at least ``min_words`` words, longest first.

    ``min_words`` defaults to the same span length the plan/target surface gate
    uses, so "substantive verbatim language" means one thing across the
    contract rather than two.
    """

    found = []
    for match in _QUOTED_SPAN_RE.finditer(text):
        span = match.group(1).strip()
        count = len(span.split())
        if count >= min_words:
            found.append((count, span))
    return tuple(sorted(found, reverse=True))


def audit_target_quotations(
    region_texts: Mapping[str, str],
    *,
    dispositions: Mapping[str, str] | None = None,
    min_words: int = 8,
) -> tuple[QuotationFinding, ...]:
    """Flag every long quotation inside target-eligible regions.

    Attribution cannot be decided mechanically - a long quoted span may be the
    author quoting a source, quoting another student, quoting a work's title, or
    quoting their own earlier writing. So this reports every long quotation and
    requires each one to carry an explicit reviewed disposition. Anything
    unaccounted for comes back with ``disposition=None``, which the caller must
    treat as a failure rather than a warning: an unreviewed long quotation in a
    target is exactly the case that would put another author's prose into the
    personalization signal.
    """

    declared = dict(dispositions or {})
    findings: list[QuotationFinding] = []
    for region_id, text in region_texts.items():
        for count, span in find_long_quotations(text, min_words=min_words):
            findings.append(
                QuotationFinding(
                    region_id=region_id,
                    words=count,
                    span=span,
                    disposition=declared.get(region_id),
                )
            )
    return tuple(findings)


# ---------------------------------------------------------------------------
# Semantic-plan fidelity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FidelityFinding:
    check: str
    detail: str
    severity: str = "fail"


@dataclass(frozen=True)
class FidelityReport:
    example_id: str
    findings: tuple[FidelityFinding, ...] = ()

    @property
    def passed(self) -> bool:
        return not any(finding.severity == "fail" for finding in self.findings)

    @property
    def failures(self) -> tuple[FidelityFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "fail")

    @property
    def warnings(self) -> tuple[FidelityFinding, ...]:
        return tuple(f for f in self.findings if f.severity == "warn")


def _plan_text(plan: Mapping[str, object], *, keys: Sequence[str]) -> str:
    parts: list[str] = []
    for key in keys:
        value = plan.get(key) or []
        if isinstance(value, str):
            parts.append(value)
        else:
            parts.extend(str(item) for item in value)  # type: ignore[union-attr]
    function = plan.get("communicative_function")
    if function:
        parts.append(str(function))
    return " ".join(parts)


# A capital that opens an item or follows sentence-ending punctuation is
# orthography, not a name, so it is not evidence of an introduced fact.
_MID_SENTENCE_NAME_RE = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-z]{2,})\b")


def _introduced_names(item: str) -> list[str]:
    return [match.group(1) for match in _MID_SENTENCE_NAME_RE.finditer(item)]


def check_plan_fidelity(
    *,
    example_id: str,
    plan: Mapping[str, object],
    target_text: str,
    region_ids: Sequence[str],
    eligible_region_ids: Iterable[str],
    max_shared_ngram: int = 8,
    max_immutable_detail_words: int = 30,
    min_atoms_per_hundred_words: float = 0.9,
) -> FidelityReport:
    """Gate one drafted plan against its immutable target.

    Implements the six Phase 5 checks. Automatable parts are decided here;
    "every major claim is represented" is approximated by atom density, which
    flags thin plans for a human rather than pretending to judge coverage.
    """

    findings: list[FidelityFinding] = []
    target_tokens = _normalised_words(target_text)
    target_lower = target_text.lower()
    atoms = [str(item) for item in (plan.get("content_atoms") or [])]  # type: ignore[union-attr]
    immutables = [str(item) for item in (plan.get("immutable_details") or [])]  # type: ignore[union-attr]
    qualifications = [
        str(item) for item in (plan.get("required_qualifications") or [])  # type: ignore[union-attr]
    ]

    # 6. The target consists only of frozen eligible regions.
    allowed = set(eligible_region_ids)
    stray = [region_id for region_id in region_ids if region_id not in allowed]
    if stray:
        findings.append(
            FidelityFinding(
                "target_regions_eligible",
                f"target draws on non-eligible region(s): {sorted(stray)}",
            )
        )

    # 1. Every major target claim is represented (density proxy).
    if not atoms:
        findings.append(FidelityFinding("claims_represented", "plan has no content atoms"))
    else:
        expected = max(2, int(len(target_tokens) / 100 * min_atoms_per_hundred_words))
        if len(atoms) < expected:
            findings.append(
                FidelityFinding(
                    "claims_represented",
                    f"{len(atoms)} content atom(s) for {len(target_tokens)} target words; "
                    f"expected at least {expected} - check for dropped claims",
                    severity="warn",
                )
            )

    # 2/3. Plan facts must come from the target: every number and every
    # capitalised name in the plan has to appear in the target text.
    for label, items in (("immutable_details", immutables), ("content_atoms", atoms)):
        for item in items:
            for number in re.findall(r"\d[\d,\.%]*", item):
                cleaned = number.rstrip(".,")
                if cleaned and cleaned not in target_text:
                    findings.append(
                        FidelityFinding(
                            "no_new_facts",
                            f"{label} introduces number {cleaned!r} absent from the target: {item!r}",
                        )
                    )
            for name in _introduced_names(item):
                if name.lower() not in target_lower:
                    findings.append(
                        FidelityFinding(
                            "no_new_facts",
                            f"{label} introduces proper noun {name!r} absent from the target: {item!r}",
                        )
                    )

    # 4. Qualifications are not lost.
    if any(marker in target_lower for marker in _HEDGE_MARKERS) and not qualifications:
        findings.append(
            FidelityFinding(
                "qualifications_preserved",
                "target hedges, contrasts or limits a claim but the plan lists no "
                "required_qualifications",
            )
        )

    # 5. The plan must not encode target wording unnecessarily. Immutable
    # details are exempt: check 3 requires them to agree with the target
    # exactly, so a name, title or figure matching is the contract working, not
    # a leak. They are length-capped instead, so a whole passage cannot be
    # smuggled in as a "detail".
    described = _plan_text(plan, keys=("content_atoms", "required_qualifications"))
    shared = _ngrams(_normalised_words(described), max_shared_ngram) & _ngrams(
        target_tokens, max_shared_ngram
    )
    if shared:
        longest = " ".join(sorted(shared)[0])
        findings.append(
            FidelityFinding(
                "no_surface_wording",
                f"plan shares a {max_shared_ngram}-word span with the target: {longest!r}",
            )
        )
    for item in immutables:
        if len(_words(item)) > max_immutable_detail_words:
            findings.append(
                FidelityFinding(
                    "no_surface_wording",
                    f"immutable detail runs {len(_words(item))} words, over the "
                    f"{max_immutable_detail_words}-word cap for a detail: {item!r}",
                )
            )

    # Style instructions are forbidden outright, wherever they appear.
    plan_blob = _plan_text(
        plan, keys=("content_atoms", "immutable_details", "required_qualifications")
    )
    for pattern, description in FORBIDDEN_PLAN_PATTERNS:
        match = re.search(pattern, plan_blob, re.IGNORECASE)
        if match:
            findings.append(
                FidelityFinding(
                    "no_style_instructions",
                    f"plan {description}: {match.group(0)!r}",
                )
            )

    return FidelityReport(example_id=example_id, findings=tuple(findings))


# ---------------------------------------------------------------------------
# Leakage gates
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeakageFinding:
    check: str
    detail: str
    fatal: bool = True


@dataclass(frozen=True)
class LeakageReport:
    findings: tuple[LeakageFinding, ...] = ()
    max_train_holdout_ngram_overlap: float = 0.0
    checks_run: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.findings

    @property
    def fatal(self) -> tuple[LeakageFinding, ...]:
        return tuple(f for f in self.findings if f.fatal)


@dataclass
class AnnotationRecord:
    """The minimum an annotation needs for the leakage gates to run."""

    example_id: str
    source_id: str
    split: str
    region_ids: tuple[str, ...]
    target_text: str
    justification: str | None = None
    flags: tuple[str, ...] = field(default_factory=tuple)


def _max_pairwise_ngram_overlap(
    left: Sequence[AnnotationRecord],
    right: Sequence[AnnotationRecord],
    size: int,
) -> tuple[float, tuple[str, str] | None]:
    best = 0.0
    worst_pair: tuple[str, str] | None = None
    right_grams = [
        (record, _ngrams(_normalised_words(record.target_text), size)) for record in right
    ]
    for record in left:
        grams = _ngrams(_normalised_words(record.target_text), size)
        if not grams:
            continue
        for other, other_grams in right_grams:
            if not other_grams:
                continue
            shared = len(grams & other_grams)
            ratio = shared / min(len(grams), len(other_grams))
            if ratio > best:
                best = ratio
                worst_pair = (record.example_id, other.example_id)
    return best, worst_pair


def run_leakage_checks(
    records: Sequence[AnnotationRecord],
    *,
    holdout_source_ids: Iterable[str],
    excluded_region_ids: Iterable[str] = (),
    other_author_source_ids: Iterable[str] = (),
    ngram_size: int = 5,
    near_duplicate_limit: float = 0.25,
) -> LeakageReport:
    """Run every Phase 7 gate over a finished annotation set."""

    holdout_ids = set(holdout_source_ids)
    excluded = set(excluded_region_ids)
    other_author = set(other_author_source_ids)
    train = [record for record in records if record.split == "train"]
    holdout = [record for record in records if record.split == "holdout"]
    findings: list[LeakageFinding] = []

    # Holdout documents may not appear in the training dataset at all.
    for record in train:
        if record.source_id in holdout_ids:
            findings.append(
                LeakageFinding(
                    "holdout_source_in_train",
                    f"{record.example_id} trains on holdout source {record.source_id}",
                )
            )
        if record.source_id in other_author:
            findings.append(
                LeakageFinding(
                    "other_author_target",
                    f"{record.example_id} targets other-author source {record.source_id}",
                )
            )
        for region_id in record.region_ids:
            if region_id in excluded:
                findings.append(
                    LeakageFinding(
                        "excluded_region_target",
                        f"{record.example_id} targets excluded region {region_id}",
                    )
                )

    # Exact target overlap across the split.
    holdout_targets = {record.target_text.strip(): record.example_id for record in holdout}
    for record in train:
        match = holdout_targets.get(record.target_text.strip())
        if match:
            findings.append(
                LeakageFinding(
                    "exact_target_overlap",
                    f"{record.example_id} target is identical to holdout {match}",
                )
            )

    # Strong near-duplicate overlap across the split.
    overlap, pair = _max_pairwise_ngram_overlap(train, holdout, ngram_size)
    if overlap > near_duplicate_limit and pair:
        findings.append(
            LeakageFinding(
                "near_duplicate_target_overlap",
                f"{pair[0]} and holdout {pair[1]} share {overlap:.1%} of their "
                f"{ngram_size}-grams (limit {near_duplicate_limit:.0%})",
            )
        )

    # A source region should ordinarily be targeted once.
    seen: dict[str, str] = {}
    for record in train:
        for region_id in record.region_ids:
            if region_id in seen:
                findings.append(
                    LeakageFinding(
                        "region_reused_across_examples",
                        f"region {region_id} is targeted by both {seen[region_id]} and "
                        f"{record.example_id}"
                        + (f" (justified: {record.justification})" if record.justification else ""),
                        fatal=record.justification is None,
                    )
                )
            else:
                seen[region_id] = record.example_id

    return LeakageReport(
        findings=tuple(findings),
        max_train_holdout_ngram_overlap=overlap,
        checks_run=(
            "holdout_source_in_train",
            "other_author_target",
            "excluded_region_target",
            "exact_target_overlap",
            "near_duplicate_target_overlap",
            "region_reused_across_examples",
        ),
    )
