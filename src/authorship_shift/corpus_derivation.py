"""Merging inherited corpus derivations with reviewed recovery overrides.

A frozen experiment's derivation is a record of what a corpus looked like when
that experiment ran. A later experiment often needs the same corpus with a few
sources re-derived - a better extractor recovers prose the original run could
not read, or a reviewed decision admits a region that was previously excluded.
Editing the frozen record to reflect that would destroy the thing that makes it
a freeze.

This module keeps both: inherited records stay byte-identical to the frozen
run, recovery overrides sit beside them, and :func:`merge_derivations` produces
the effective derivation for the later experiment while recording which of the
two each source came from.

The integrity property worth having is that a recovery may re-derive *text*,
but never silently re-point at different *bytes*. An override whose
``artifact_sha256`` disagrees with the record it supersedes is a different
source document wearing the same ``source_id``, and is rejected unless the
caller states the substitution explicitly.

Nothing here reads a document or decides eligibility. It composes records that
an extraction pipeline and a human review have already produced.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Iterable, Mapping, Sequence

CORPUS_DERIVATION_SCHEMA_VERSION = 1

# Where an effective record came from.
ORIGIN_INHERITED = "inherited"
ORIGIN_RECOVERED = "recovered"
ORIGINS = (ORIGIN_INHERITED, ORIGIN_RECOVERED)

# Provenance classes whose words belong to the personalization target
# distribution. `other_author` and `unresolved` are deliberately absent.
DEFAULT_ACCEPTED_CLASSES = ("self_authored", "ai_assisted_accepted")


@dataclass(frozen=True)
class SourceDerivation:
    """One source's derived state: what was read, and how much of it is usable.

    ``eligible_words`` is post-exclusion: it counts only regions that survived
    both the mechanical rules and the reviewed mask, so summing it across
    records gives a corpus total directly.
    """

    source_id: str
    provenance_class: str
    artifact_sha256: str
    extractor_name: str
    extractor_version: str
    extraction_mode: str
    extracted_text_sha256: str
    eligible_words: int
    target_units: int
    eligible_region_ids: tuple[str, ...] = ()
    excluded: tuple[tuple[str, int], ...] = ()
    origin: str = ORIGIN_INHERITED
    supersedes_extracted_text_sha256: str | None = None
    note: str | None = None
    extra: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.origin not in ORIGINS:
            raise ValueError(f"{self.source_id}: unknown origin {self.origin!r}")
        if self.eligible_words < 0 or self.target_units < 0:
            raise ValueError(f"{self.source_id}: negative counts are not derivable")

    @property
    def contributes_words(self) -> bool:
        return self.eligible_words > 0

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_id": self.source_id,
            "provenance_class": self.provenance_class,
            "artifact_sha256": self.artifact_sha256,
            "extractor_name": self.extractor_name,
            "extractor_version": self.extractor_version,
            "extraction_mode": self.extraction_mode,
            "extracted_text_sha256": self.extracted_text_sha256,
            "eligible_words": self.eligible_words,
            "target_units": self.target_units,
            "eligible_region_ids": list(self.eligible_region_ids),
            "excluded": [{"reason": reason, "words": words} for reason, words in self.excluded],
            "origin": self.origin,
        }
        if self.supersedes_extracted_text_sha256:
            payload["supersedes_extracted_text_sha256"] = self.supersedes_extracted_text_sha256
        if self.note:
            payload["note"] = self.note
        if self.extra:
            payload["extra"] = dict(self.extra)
        return payload


class DerivationConflict(ValueError):
    """An override contradicts the inherited record it claims to supersede."""


def merge_derivations(
    inherited: Sequence[SourceDerivation],
    overrides: Sequence[SourceDerivation],
    *,
    allow_artifact_substitution: Iterable[str] = (),
) -> tuple[SourceDerivation, ...]:
    """Apply recovery overrides on top of inherited records.

    An override replaces the inherited record for its ``source_id`` and is
    tagged :data:`ORIGIN_RECOVERED`, carrying the superseded extracted-text
    digest so the substitution stays auditable. Sources present only in
    ``overrides`` are new to this experiment and are kept as-is.

    Ordering follows ``inherited`` first, then any override-only sources in
    their given order, so the merged sequence is deterministic.

    Raises :class:`DerivationConflict` when an override points at different
    artifact bytes than the record it supersedes. Genuine re-scans of a
    re-exported file are legitimate but must be named in
    ``allow_artifact_substitution`` rather than passing silently.
    """

    by_id = {record.source_id: record for record in inherited}
    if len(by_id) != len(inherited):
        raise DerivationConflict("inherited records contain a duplicate source_id")

    permitted = set(allow_artifact_substitution)
    overridden: dict[str, SourceDerivation] = {}
    for override in overrides:
        source_id = override.source_id
        if source_id in overridden:
            raise DerivationConflict(f"{source_id}: two overrides for one source")
        previous = by_id.get(source_id)
        if previous is not None:
            if (
                previous.artifact_sha256 != override.artifact_sha256
                and source_id not in permitted
            ):
                raise DerivationConflict(
                    f"{source_id}: override artifact_sha256 "
                    f"{override.artifact_sha256[:12]}... does not match inherited "
                    f"{previous.artifact_sha256[:12]}... - a recovery may re-derive text "
                    f"but not silently change which bytes it came from"
                )
            override = replace(
                override,
                origin=ORIGIN_RECOVERED,
                supersedes_extracted_text_sha256=(
                    override.supersedes_extracted_text_sha256
                    or previous.extracted_text_sha256
                ),
            )
        else:
            override = replace(override, origin=ORIGIN_RECOVERED)
        overridden[source_id] = override

    merged = [overridden.get(record.source_id, record) for record in inherited]
    merged.extend(
        override for source_id, override in overridden.items() if source_id not in by_id
    )
    return tuple(merged)


def corpus_accounting(
    records: Sequence[SourceDerivation],
    *,
    accepted_classes: Sequence[str] = DEFAULT_ACCEPTED_CLASSES,
) -> dict[str, Any]:
    """Total a merged derivation by provenance class and by record origin.

    Only ``accepted_classes`` count toward the corpus. Everything else is
    reported under ``excluded_documents`` with its class and word count, so a
    quarantined or unresolved source is visibly accounted for rather than
    silently missing.
    """

    accepted = [r for r in records if r.provenance_class in accepted_classes]
    excluded = [r for r in records if r.provenance_class not in accepted_classes]

    by_class: dict[str, dict[str, int]] = {}
    for record in accepted:
        bucket = by_class.setdefault(record.provenance_class, {"documents": 0, "words": 0})
        bucket["documents"] += 1
        bucket["words"] += record.eligible_words

    by_origin: dict[str, dict[str, int]] = {}
    for record in accepted:
        bucket = by_origin.setdefault(record.origin, {"documents": 0, "words": 0})
        bucket["documents"] += 1
        bucket["words"] += record.eligible_words

    return {
        "schema_version": CORPUS_DERIVATION_SCHEMA_VERSION,
        "documents": len(accepted),
        "words": sum(r.eligible_words for r in accepted),
        "target_units": sum(r.target_units for r in accepted),
        "by_provenance_class": by_class,
        "by_origin": by_origin,
        "zero_word_accepted_documents": sorted(
            r.source_id for r in accepted if not r.contributes_words
        ),
        "excluded_documents": [
            {
                "source_id": r.source_id,
                "provenance_class": r.provenance_class,
                "eligible_words": r.eligible_words,
            }
            for r in excluded
        ],
    }
