from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .text_derivation import (
    CORRECTION_KEYS,
    CORRECTIONS_SCHEMA_VERSION,
    PageText,
    corrections_sha256,
    pages_sha256,
)


@dataclass(frozen=True)
class _PlannedReplacement:
    index: int
    page: int
    start: int
    end: int
    old: str
    new: str


def _nonoverlapping_spans(text: str, needle: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        found = text.find(needle, start)
        if found < 0:
            break
        end = found + len(needle)
        spans.append((found, end))
        start = end
    return spans


def apply_reviewed_corrections_order_invariant(
    pages: Iterable[PageText],
    correction_payload: dict[str, Any] | None,
    *,
    artifact_sha256: str,
) -> tuple[list[PageText], str | None]:
    """Apply reviewed corrections against the original page text, simultaneously.

    Every rule is validated against the unmodified base extraction. If two rules
    claim overlapping source characters, the ledger is rejected rather than
    relying on rule order. Applying replacements from right to left then makes the
    result invariant to ledger ordering and prevents one rule from creating text
    that a later rule can accidentally rewrite.
    """

    rows = [PageText(row.page, row.text) for row in pages]
    if correction_payload is None:
        return rows, None
    if correction_payload.get("schema_version") != CORRECTIONS_SCHEMA_VERSION:
        raise ValueError(
            f"corrections schema_version must be {CORRECTIONS_SCHEMA_VERSION}"
        )
    if correction_payload.get("artifact_sha256") != artifact_sha256:
        raise ValueError("corrections artifact_sha256 does not match reviewed PDF")

    base_hash = pages_sha256(rows)
    if correction_payload.get("base_text_sha256") != base_hash:
        raise ValueError("corrections base_text_sha256 does not match extracted base text")

    replacements = correction_payload.get("replacements")
    if not isinstance(replacements, list):
        raise ValueError("corrections replacements must be a list")

    page_map = {row.page: row.text for row in rows}
    planned_by_page: dict[int, list[_PlannedReplacement]] = {}

    for index, replacement in enumerate(replacements, start=1):
        if not isinstance(replacement, dict):
            raise ValueError(f"correction {index}: replacement must be an object")
        unknown = sorted(set(replacement) - CORRECTION_KEYS)
        if unknown:
            raise ValueError(
                f"correction {index}: unknown key(s) {', '.join(unknown)}; "
                f"allowed keys are {', '.join(sorted(CORRECTION_KEYS))}"
            )
        try:
            page_number = int(replacement["page"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"correction {index}: page must be an integer") from exc
        if page_number not in page_map:
            raise ValueError(f"correction {index}: page {page_number} is absent")

        old = str(replacement.get("old", ""))
        new = str(replacement.get("new", ""))
        if not old:
            raise ValueError(f"correction {index}: old text is required")
        if old == new:
            raise ValueError(f"correction {index}: no-op replacement is not allowed")
        try:
            expected_count = int(replacement["expected_count"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(
                f"correction {index}: expected_count is required and must be an integer"
            ) from exc
        if expected_count < 1:
            raise ValueError(f"correction {index}: expected_count must be at least 1")

        spans = _nonoverlapping_spans(page_map[page_number], old)
        if len(spans) != expected_count:
            raise ValueError(
                f"correction {index}: page {page_number} expected {expected_count} "
                f"occurrence(s) of {old!r}, found {len(spans)}"
            )
        for start, end in spans:
            planned_by_page.setdefault(page_number, []).append(
                _PlannedReplacement(index, page_number, start, end, old, new)
            )

    corrected_pages: list[PageText] = []
    for page_number in sorted(page_map):
        text = page_map[page_number]
        planned = sorted(
            planned_by_page.get(page_number, []),
            key=lambda item: (item.start, item.end, item.index),
        )
        for left, right in zip(planned, planned[1:]):
            if right.start < left.end:
                raise ValueError(
                    f"corrections {left.index} and {right.index}: page {page_number} "
                    "claim overlapping source text; make the shorter rule more specific "
                    "or remove one rule"
                )
        for item in reversed(planned):
            text = text[: item.start] + item.new + text[item.end :]
        corrected_pages.append(PageText(page_number, text))

    return corrected_pages, corrections_sha256(correction_payload)
