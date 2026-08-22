import json

from authorship_shift.annotation_integrity import frozen_packet_sha256
from authorship_shift.text_derivation import (
    EXTRACTOR_NAME,
    EXTRACTOR_VERSION,
    EXTRACTION_MODE,
    NORMALIZATION_VERSION,
    PageText,
    apply_reviewed_corrections,
    canonical_text_contains,
    corrections_sha256,
    normalize_pdf_text,
    pages_sha256,
    parse_registry_text_derivation,
    write_canonical_extraction,
)


def test_safe_normalization_expands_ligatures_but_not_ambiguous_repairs():
    raw = "Di\ufb00erence\u00a0here\tplus  spacing\r\nT reasury\r\nguar-\nantees"
    normalized = normalize_pdf_text(raw)
    assert "Difference here plus spacing" in normalized
    assert "T reasury" in normalized
    assert "guar-\nantees" in normalized


def test_reviewed_corrections_are_page_scoped_and_hashable():
    pages = [PageText(1, "T reasury provides guar-\nantees."), PageText(2, "Other text.")]
    artifact_hash = "a" * 64
    payload = {
        "schema_version": 1,
        "artifact_sha256": artifact_hash,
        "base_text_sha256": pages_sha256(pages),
        "replacements": [
            {"page": 1, "old": "T reasury", "new": "Treasury", "expected_count": 1},
            {"page": 1, "old": "guar-\nantees", "new": "guarantees", "expected_count": 1},
        ],
    }
    corrected, digest = apply_reviewed_corrections(
        pages,
        payload,
        artifact_sha256=artifact_hash,
    )
    assert corrected[0].text == "Treasury provides guarantees."
    assert digest == corrections_sha256(payload)


def test_reviewed_correction_refuses_drift():
    pages = [PageText(1, "T reasury")]
    payload = {
        "schema_version": 1,
        "artifact_sha256": "a" * 64,
        "base_text_sha256": pages_sha256(pages),
        "replacements": [
            {"page": 1, "old": "T reasury", "new": "Treasury", "expected_count": 2}
        ],
    }
    try:
        apply_reviewed_corrections(pages, payload, artifact_sha256="a" * 64)
    except ValueError as exc:
        assert "expected 2" in str(exc)
    else:
        raise AssertionError("correction ledger must fail if source text drifted")


def test_target_may_reflow_whitespace_but_not_change_characters():
    pages = [PageText(1, "The federal government supports\nsome private activities.")]
    assert canonical_text_contains(
        pages,
        "The federal government supports some private activities.",
    )
    assert not canonical_text_contains(
        pages,
        "The federal government supported some private activities.",
    )


def test_registry_derivation_matches_local_canonical_output(tmp_path):
    pages = [PageText(1, "Treasury provides guarantees."), PageText(2, "Second page.")]
    artifact_hash = "a" * 64
    canonical_path = tmp_path / "cbo-62265.canonical.json"
    payload = write_canonical_extraction(
        canonical_path,
        source_id="cbo-62265",
        artifact_sha256=artifact_hash,
        base_pages=pages,
        canonical_pages=pages,
        correction_hash=None,
    )
    row = {
        "source_id": "cbo-62265",
        "status": "approved",
        "source_snapshot": {
            "sha256": artifact_hash,
            "artifact_kind": "pdf",
        },
        "source_text_derivation": {
            "artifact_sha256": artifact_hash,
            "extractor_name": EXTRACTOR_NAME,
            "extractor_version": EXTRACTOR_VERSION,
            "extraction_mode": EXTRACTION_MODE,
            "normalization_version": NORMALIZATION_VERSION,
            "base_text_sha256": payload["base_text_sha256"],
            "corrections_sha256": None,
            "canonical_text_sha256": payload["canonical_text_sha256"],
            "canonical_text_path": canonical_path.name,
        },
    }
    derivation, errors = parse_registry_text_derivation(row, registry_dir=tmp_path)
    assert errors == []
    assert derivation is not None
    assert derivation.canonical_text_sha256 == payload["canonical_text_sha256"]


def test_approved_pdf_requires_derivation(tmp_path):
    row = {
        "source_id": "cbo-62265",
        "status": "approved",
        "source_snapshot": {"sha256": "a" * 64, "artifact_kind": "pdf"},
    }
    derivation, errors = parse_registry_text_derivation(row, registry_dir=tmp_path)
    assert derivation is None
    assert any("requires source_text_derivation" in error for error in errors)


def test_text_derivation_is_part_of_frozen_packet_fingerprint():
    packet = {
        "id": "ex-1",
        "genre": "business_analysis",
        "split": "train",
        "instruction": "Explain the finding.",
        "target_text": "Treasury provides guarantees.",
        "provenance": {"kind": "public_domain", "source_id": "cbo-62265"},
        "metadata": {
            "source_snapshot": {"sha256": "a" * 64},
            "source_text_derivation": {
                "artifact_sha256": "a" * 64,
                "extractor_name": EXTRACTOR_NAME,
                "extractor_version": EXTRACTOR_VERSION,
                "extraction_mode": EXTRACTION_MODE,
                "normalization_version": NORMALIZATION_VERSION,
                "base_text_sha256": "b" * 64,
                "corrections_sha256": None,
                "canonical_text_sha256": "c" * 64,
            },
        },
    }
    before = frozen_packet_sha256(packet)
    packet["metadata"]["source_text_derivation"]["canonical_text_sha256"] = "d" * 64
    assert frozen_packet_sha256(packet) != before
