"""Conservative checks for factual-looking details added by a candidate.

The immutable precheck answers only one direction of fidelity: did source details
survive? This module covers a narrow part of the opposite direction by flagging
TitleCase-like identifiers that appear inside a sentence even though they never
appear in the locked source.

It is intentionally conservative. Sentence-initial capitalization is ignored,
acronyms are ignored, and this is not a general fact checker. Its purpose is to
catch high-confidence additions such as introducing real company or product names
into a source that named none.
"""

from __future__ import annotations

import re

from .metrics import words

# Requiring a lowercase second character keeps this focused on TitleCase-like
# names (Sony, Toshiba, Microsoft) rather than abbreviations such as AI, R&D, EV,
# or API, which may be legitimate lexical compression rather than new entities.
_TITLECASE_TOKEN_RE = re.compile(r"\b[A-Z][a-z][A-Za-z0-9&.-]*\b")
# Treat punctuation that commonly starts a fresh clause as a boundary for this
# conservative check. This deliberately trades recall for fewer false positives.
_CLAUSE_BOUNDARIES = set(".!?;:—")
_OPENING_PUNCTUATION = set('"\'“‘([{')


def _is_clause_initial(text: str, start: int) -> bool:
    index = start - 1
    while index >= 0 and (text[index].isspace() or text[index] in _OPENING_PUNCTUATION):
        index -= 1
    return index < 0 or text[index] in _CLAUSE_BOUNDARIES


def added_name_hits(source: str, candidate: str) -> list[str]:
    """Return high-confidence TitleCase names added by ``candidate``.

    A hit must:
    - look like a TitleCase identifier rather than an acronym;
    - occur away from the start of a sentence/clause; and
    - not occur as a token anywhere in the locked source, case-insensitively.

    The function therefore catches constructions such as ``When Sony and Toshiba
    ...`` when neither company appears in the source, while ignoring ordinary
    capitalization at the start of a sentence and abbreviations such as ``R&D``.
    It does not claim to detect all fabricated details.
    """

    source_tokens = set(words(source))
    hits: set[str] = set()
    for match in _TITLECASE_TOKEN_RE.finditer(candidate):
        token = match.group(0)
        if token.lower() in source_tokens:
            continue
        if _is_clause_initial(candidate, match.start()):
            continue
        hits.add(token)
    return sorted(hits, key=lambda value: (value.lower(), value))
