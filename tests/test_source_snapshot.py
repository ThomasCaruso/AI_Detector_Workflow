import json

from authorship_shift.annotation_integrity import (
    build_frozen_manifest,
    frozen_packet_sha256,
)
from authorship_shift.source_snapshot import load_registry_snapshots, parse_source_snapshot


def _registry(source):
    return {"schema_version": 1, "sources": [source]}


def _external_source(*, status="approved", snapshot=None):
    row = {
        "source_id": "gao-26-108140",
        "title": "Weapon System Sustainment",
        "genre": "business_analysis",
        "status": status,
        "provenance_kind": "public_domain",
        "rights_basis": "U.S. Government work; exact artifact reviewed for third-party material.",
        "canonical_url": "https://www.gao.gov/products/gao-26-108140",
        "license": "Public Domain (U.S. Government work)",
    }
    if snapshot is not None:
        row["source_snapshot"] = snapshot
    return row


def _snapshot():
    return {
        "retrieved_at": "2026-08-21T23:30:00Z",
        "sha256": "a" * 64,
        "artifact_kind": "pdf",
        "revision_label": "Published Apr 23, 2026",
    }


def test_approved_external_source_requires_exact_snapshot(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(_registry(_external_source())), encoding="utf-8")
    snapshots, errors = load_registry_snapshots(path)
    assert snapshots == {}
    assert any("requires source_snapshot" in item for item in errors)


def test_candidate_external_source_may_be_unsnapshotted(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(_registry(_external_source(status="candidate"))),
        encoding="utf-8",
    )
    snapshots, errors = load_registry_snapshots(path)
    assert snapshots == {}
    assert errors == []


def test_valid_snapshot_is_normalized_and_revision_is_optional():
    parsed = parse_source_snapshot(_snapshot(), source_id="gao")
    assert parsed.sha256 == "a" * 64
    assert parsed.artifact_kind == "pdf"
    assert parsed.revision_label == "Published Apr 23, 2026"


def test_bad_snapshot_hash_and_timestamp_are_rejected(tmp_path):
    bad = _snapshot()
    bad["sha256"] = "not-a-hash"
    bad["retrieved_at"] = "yesterday"
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(_registry(_external_source(snapshot=bad))),
        encoding="utf-8",
    )
    _, errors = load_registry_snapshots(path)
    assert errors
    assert any("retrieved_at" in item or "sha256" in item for item in errors)


def test_source_snapshot_is_part_of_frozen_packet_contract():
    packet = {
        "id": "ex-1",
        "genre": "business_analysis",
        "split": "train",
        "instruction": "Explain the finding.",
        "target_text": "Human-authored prose.",
        "provenance": {"kind": "public_domain", "source_id": "gao"},
        "metadata": {"source_snapshot": _snapshot()},
    }
    before = frozen_packet_sha256(packet)
    packet["metadata"]["source_snapshot"]["sha256"] = "b" * 64
    after = frozen_packet_sha256(packet)
    assert before != after
    manifest = build_frozen_manifest([packet])
    assert "metadata.source_snapshot" in manifest["frozen_fields"]
