from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any

from .corpus_pipeline import RawExcerpt
from .text_derivation import PageText

ALLOWED_EXCLUSION_CATEGORIES = {"rights", "style"}
EXCLUSION_KEYS = frozenset({"pages", "category", "reason"})


@dataclass(frozen=True)
class SourceExclusion:
    pages: tuple[int, ...]
    category: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["pages"] = list(self.pages)
        return payload


def load_registry_source_exclusions(
    registry_path: str | Path,
) -> tuple[dict[str, tuple[SourceExclusion, ...]], list[str]]:
    try:
        raw = json.loads(Path(registry_path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        return {}, [f"source registry could not be read for exclusions: {exc}"]

    rows = raw.get("sources", []) if isinstance(raw, dict) else []
    if not isinstance(rows, list):
        return {}, ["source registry requires a sources list"]

    result: dict[str, tuple[SourceExclusion, ...]] = {}
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id", "")).strip() or f"source line {index}"
        payload = row.get("source_exclusions")
        if payload is None:
            result[source_id] = tuple()
            continue
        if not isinstance(payload, list):
            errors.append(f"{source_id}: source_exclusions must be a list")
            continue

        parsed: list[SourceExclusion] = []
        for exclusion_index, item in enumerate(payload, start=1):
            where = f"{source_id}: source_exclusions[{exclusion_index}]"
            if not isinstance(item, dict):
                errors.append(f"{where} must be an object")
                continue
            unknown = sorted(set(item) - EXCLUSION_KEYS)
            if unknown:
                errors.append(
                    f"{where} unknown key(s) {', '.join(unknown)}; allowed keys are "
                    + ", ".join(sorted(EXCLUSION_KEYS))
                )
                continue
            pages = item.get("pages")
            if not isinstance(pages, list) or not pages:
                errors.append(f"{where}.pages must be a non-empty list")
                continue
            try:
                normalized_pages = tuple(sorted({int(page) for page in pages}))
            except (TypeError, ValueError):
                errors.append(f"{where}.pages must contain positive integers")
                continue
            if any(page < 1 for page in normalized_pages):
                errors.append(f"{where}.pages must contain positive integers")
                continue
            category = str(item.get("category", "")).strip()
            if category not in ALLOWED_EXCLUSION_CATEGORIES:
                errors.append(
                    f"{where}.category must be one of {sorted(ALLOWED_EXCLUSION_CATEGORIES)}"
                )
                continue
            reason = str(item.get("reason", "")).strip()
            if not reason:
                errors.append(f"{where}.reason is required")
                continue
            parsed.append(
                SourceExclusion(
                    pages=normalized_pages,
                    category=category,
                    reason=reason,
                )
            )
        result[source_id] = tuple(parsed)
    return result, errors


def excerpt_source_pages(excerpt: RawExcerpt) -> tuple[int, ...]:
    value = excerpt.metadata.get("source_pages")
    if not isinstance(value, list) or not value:
        raise ValueError(
            f"{excerpt.id}: PDF raw excerpt metadata.source_pages must be a non-empty list"
        )
    try:
        pages = tuple(sorted({int(page) for page in value}))
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"{excerpt.id}: metadata.source_pages must contain positive integers"
        ) from exc
    if any(page < 1 for page in pages):
        raise ValueError(
            f"{excerpt.id}: metadata.source_pages must contain positive integers"
        )
    return pages


def validate_excerpt_pages(
    excerpt: RawExcerpt,
    canonical_pages: list[PageText],
    exclusions: tuple[SourceExclusion, ...],
) -> tuple[int, ...]:
    pages = excerpt_source_pages(excerpt)
    page_map = {row.page: row.text for row in canonical_pages}
    missing = [page for page in pages if page not in page_map]
    if missing:
        raise ValueError(
            f"{excerpt.id}: metadata.source_pages reference absent canonical page(s) {missing}"
        )

    for exclusion in exclusions:
        overlap = sorted(set(pages) & set(exclusion.pages))
        if overlap:
            raise ValueError(
                f"{excerpt.id}: source page(s) {overlap} are excluded for "
                f"{exclusion.category}: {exclusion.reason}"
            )

    canonical = " ".join(
        " ".join(page_map[page].split())
        for page in pages
    )
    target = " ".join(excerpt.target_text.split())
    if not target or target not in canonical:
        raise ValueError(
            f"{excerpt.id}: target_text is not a whitespace-only reflow of the frozen "
            f"canonical extraction on declared source_pages {list(pages)}"
        )
    return pages
