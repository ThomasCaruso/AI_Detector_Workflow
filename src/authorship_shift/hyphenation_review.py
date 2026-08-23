from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Iterable

from .text_derivation import PageText

_LINEBREAK_HYPHEN_RE = re.compile(r"(?P<left>[A-Za-z]{2,})-\n(?P<right>[A-Za-z]{2,})")


@dataclass(frozen=True)
class HyphenationSuggestion:
    page: int
    old: str
    joined_form: str
    hyphenated_form: str
    joined_evidence_count: int
    hyphenated_evidence_count: int
    verdict: str
    proposed_new: str | None
    expected_count: int

    def to_dict(self) -> dict:
        return asdict(self)


def _whole_word_count(text: str, form: str) -> int:
    pattern = re.compile(
        rf"(?<![A-Za-z]){re.escape(form)}(?![A-Za-z])",
        flags=re.IGNORECASE,
    )
    return len(pattern.findall(text))


def suggest_linebreak_hyphenation(
    pages: Iterable[PageText],
) -> list[HyphenationSuggestion]:
    """Classify PDF line-break hyphens from same-document evidence only.

    This function is advisory. It never changes canonical text and never writes a
    correction ledger. JOIN means the closed form occurs elsewhere and the
    hyphenated form does not; KEEP means the inverse; CONFLICT means both occur;
    UNRESOLVED means neither occurs. Every actual repair must still be reviewed
    and entered explicitly in the page-scoped correction ledger.
    """

    rows = sorted((PageText(row.page, row.text) for row in pages), key=lambda row: row.page)
    corpus = "\n".join(row.text for row in rows)
    suggestions: list[HyphenationSuggestion] = []

    for row in rows:
        grouped: dict[str, tuple[str, str, int]] = {}
        for match in _LINEBREAK_HYPHEN_RE.finditer(row.text):
            old = match.group(0)
            left = match.group("left")
            right = match.group("right")
            if old in grouped:
                prev_left, prev_right, count = grouped[old]
                grouped[old] = (prev_left, prev_right, count + 1)
            else:
                grouped[old] = (left, right, 1)

        for old, (left, right, expected_count) in sorted(grouped.items()):
            joined = left + right
            hyphenated = left + "-" + right
            joined_count = _whole_word_count(corpus, joined)
            hyphenated_count = _whole_word_count(corpus, hyphenated)

            if joined_count > 0 and hyphenated_count == 0:
                verdict = "JOIN"
                proposed_new: str | None = joined
            elif hyphenated_count > 0 and joined_count == 0:
                verdict = "KEEP"
                proposed_new = hyphenated
            elif joined_count > 0 and hyphenated_count > 0:
                verdict = "CONFLICT"
                proposed_new = None
            else:
                verdict = "UNRESOLVED"
                proposed_new = None

            suggestions.append(
                HyphenationSuggestion(
                    page=row.page,
                    old=old,
                    joined_form=joined,
                    hyphenated_form=hyphenated,
                    joined_evidence_count=joined_count,
                    hyphenated_evidence_count=hyphenated_count,
                    verdict=verdict,
                    proposed_new=proposed_new,
                    expected_count=expected_count,
                )
            )

    return suggestions
