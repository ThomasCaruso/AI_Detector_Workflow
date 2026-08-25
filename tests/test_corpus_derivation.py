"""Tests for merging inherited derivations with reviewed recovery overrides.

Every record here is synthetic: invented source ids, invented digests, no real
corpus document and no user prose.
"""

from __future__ import annotations

import pytest

from authorship_shift.corpus_derivation import (
    CORPUS_DERIVATION_SCHEMA_VERSION,
    DEFAULT_ACCEPTED_CLASSES,
    ORIGIN_INHERITED,
    ORIGIN_RECOVERED,
    DerivationConflict,
    SourceDerivation,
    corpus_accounting,
    merge_derivations,
)


def _record(
    source_id: str,
    *,
    provenance_class: str = "self_authored",
    artifact: str = "a" * 64,
    text: str = "b" * 64,
    words: int = 100,
    units: int = 1,
    mode: str = "plain",
    origin: str = ORIGIN_INHERITED,
) -> SourceDerivation:
    return SourceDerivation(
        source_id=source_id,
        provenance_class=provenance_class,
        artifact_sha256=artifact,
        extractor_name="synthetic",
        extractor_version="v1",
        extraction_mode=mode,
        extracted_text_sha256=text,
        eligible_words=words,
        target_units=units,
        origin=origin,
    )


def test_inherited_records_pass_through_untouched():
    inherited = [_record("alpha"), _record("beta", words=250, units=2)]

    merged = merge_derivations(inherited, [])

    assert [r.source_id for r in merged] == ["alpha", "beta"]
    assert all(r.origin == ORIGIN_INHERITED for r in merged)
    assert merged == tuple(inherited)


def test_override_replaces_inherited_record_and_is_tagged_recovered():
    inherited = [_record("alpha", text="c" * 64, words=0, units=0)]
    override = _record("alpha", text="d" * 64, words=816, units=3, mode="layout")

    merged = merge_derivations(inherited, [override])

    assert len(merged) == 1
    recovered = merged[0]
    assert recovered.origin == ORIGIN_RECOVERED
    assert recovered.eligible_words == 816
    assert recovered.extraction_mode == "layout"


def test_override_records_the_digest_it_superseded():
    inherited = [_record("alpha", text="c" * 64, words=0)]
    override = _record("alpha", text="d" * 64, words=816)

    merged = merge_derivations(inherited, [override])

    assert merged[0].supersedes_extracted_text_sha256 == "c" * 64


def test_override_may_not_silently_change_artifact_bytes():
    inherited = [_record("alpha", artifact="a" * 64)]
    override = _record("alpha", artifact="e" * 64)

    with pytest.raises(DerivationConflict, match="does not match inherited"):
        merge_derivations(inherited, [override])


def test_artifact_substitution_is_allowed_when_named_explicitly():
    inherited = [_record("alpha", artifact="a" * 64)]
    override = _record("alpha", artifact="e" * 64)

    merged = merge_derivations(
        inherited, [override], allow_artifact_substitution=["alpha"]
    )

    assert merged[0].artifact_sha256 == "e" * 64
    assert merged[0].origin == ORIGIN_RECOVERED


def test_override_only_source_is_appended_as_recovered():
    inherited = [_record("alpha")]
    override = _record("gamma", words=42)

    merged = merge_derivations(inherited, [override])

    assert [r.source_id for r in merged] == ["alpha", "gamma"]
    assert merged[1].origin == ORIGIN_RECOVERED
    assert merged[1].supersedes_extracted_text_sha256 is None


def test_merge_ordering_is_deterministic():
    inherited = [_record("alpha"), _record("beta"), _record("delta")]
    overrides = [_record("delta", words=5), _record("gamma", words=7)]

    first = merge_derivations(inherited, overrides)
    second = merge_derivations(inherited, overrides)

    assert [r.source_id for r in first] == ["alpha", "beta", "delta", "gamma"]
    assert first == second


def test_two_overrides_for_one_source_is_a_conflict():
    inherited = [_record("alpha")]

    with pytest.raises(DerivationConflict, match="two overrides"):
        merge_derivations(inherited, [_record("alpha"), _record("alpha")])


def test_duplicate_inherited_source_id_is_a_conflict():
    with pytest.raises(DerivationConflict, match="duplicate source_id"):
        merge_derivations([_record("alpha"), _record("alpha")], [])


def test_unknown_origin_is_rejected():
    with pytest.raises(ValueError, match="unknown origin"):
        _record("alpha", origin="guessed")


def test_negative_counts_are_rejected():
    with pytest.raises(ValueError, match="negative counts"):
        SourceDerivation(
            source_id="alpha",
            provenance_class="self_authored",
            artifact_sha256="a" * 64,
            extractor_name="synthetic",
            extractor_version="v1",
            extraction_mode="plain",
            extracted_text_sha256="b" * 64,
            eligible_words=-1,
            target_units=0,
        )


def test_accounting_totals_by_class_and_origin():
    records = merge_derivations(
        [
            _record("alpha", words=100),
            _record("beta", provenance_class="ai_assisted_accepted", words=250),
            _record("gamma", words=0, units=0),
        ],
        [_record("gamma", words=80, units=1)],
    )

    report = corpus_accounting(records)

    assert report["documents"] == 3
    assert report["words"] == 430
    assert report["by_provenance_class"]["self_authored"]["words"] == 180
    assert report["by_provenance_class"]["ai_assisted_accepted"]["words"] == 250
    assert report["by_origin"][ORIGIN_RECOVERED]["words"] == 80
    assert report["by_origin"][ORIGIN_INHERITED]["words"] == 350


def test_accounting_excludes_non_accepted_classes_but_still_reports_them():
    records = [
        _record("alpha", words=100),
        _record("quarantined", provenance_class="other_author", words=2518),
        _record("open-question", provenance_class="unresolved", words=0),
    ]

    report = corpus_accounting(records)

    assert report["documents"] == 1
    assert report["words"] == 100
    excluded = {row["source_id"]: row for row in report["excluded_documents"]}
    assert excluded["quarantined"]["provenance_class"] == "other_author"
    assert excluded["quarantined"]["eligible_words"] == 2518
    assert "open-question" in excluded


def test_accounting_flags_accepted_documents_contributing_no_words():
    records = [_record("alpha", words=100), _record("silent", words=0, units=0)]

    report = corpus_accounting(records)

    assert report["zero_word_accepted_documents"] == ["silent"]


def test_accepted_classes_are_configurable():
    records = [
        _record("alpha", words=100),
        _record("beta", provenance_class="ai_assisted_accepted", words=250),
    ]

    report = corpus_accounting(records, accepted_classes=("self_authored",))

    assert report["words"] == 100
    assert [row["source_id"] for row in report["excluded_documents"]] == ["beta"]


def test_default_accepted_classes_exclude_other_author_and_unresolved():
    assert DEFAULT_ACCEPTED_CLASSES == ("self_authored", "ai_assisted_accepted")


def test_as_dict_round_trips_the_audit_fields():
    merged = merge_derivations(
        [_record("alpha", text="c" * 64, words=0)],
        [_record("alpha", text="d" * 64, words=816, mode="layout")],
    )

    payload = merged[0].as_dict()

    assert payload["origin"] == ORIGIN_RECOVERED
    assert payload["supersedes_extracted_text_sha256"] == "c" * 64
    assert payload["extraction_mode"] == "layout"
    assert payload["eligible_words"] == 816


def test_excluded_reasons_are_reported_as_pairs():
    record = SourceDerivation(
        source_id="alpha",
        provenance_class="self_authored",
        artifact_sha256="a" * 64,
        extractor_name="synthetic",
        extractor_version="v1",
        extraction_mode="layout",
        extracted_text_sha256="b" * 64,
        eligible_words=816,
        target_units=3,
        excluded=(("assignment_title", 2),),
    )

    assert record.as_dict()["excluded"] == [{"reason": "assignment_title", "words": 2}]


def test_schema_version_is_pinned():
    assert CORPUS_DERIVATION_SCHEMA_VERSION == 1
