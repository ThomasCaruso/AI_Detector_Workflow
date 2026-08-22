import json

from authorship_shift.annotation_integrity import (
    build_frozen_manifest,
    frozen_packet_sha256,
)
from authorship_shift.source_snapshot import (
    load_registry_snapshots,
    parse_source_snapshot,
    snapshot_set_sha256,
)


def _registry(source):
    return {"schema_version": 1, "sources": [source]}


def _source(*, status="approved", kind="public_domain", snapshot=None):
    row = {
        "source_id": "source-1",
        "title": "Reviewed source",
        "genre": "business_analysis",
        "status": status,
        "provenance_kind": kind,
        "rights_basis": "Reviewed rights basis.",
        "canonical_url": "https://example.gov/source" if kind in {"public_domain", "licensed"} else None,
        "license": "Public Domain (U.S. Government work)" if kind == "public_domain" else None,
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


def test_every_approved_source_requires_exact_snapshot(tmp_path):
    for kind in ("public_domain", "user_owned", "consented"):
        path = tmp_path / f"{kind}.json"
        path.write_text(json.dumps(_registry(_source(kind=kind))), encoding="utf-8")
        snapshots, errors = load_registry_snapshots(path)
        assert snapshots == {}
        assert any("requires source_snapshot" in item for item in errors)


def test_candidate_source_may_keep_empty_snapshot_placeholder(tmp_path):
    candidate = _source(
        status="candidate",
        snapshot={
            "retrieved_at": None,
            "sha256": None,
            "artifact_kind": None,
            "revision_label": None,
        },
    )
    path = tmp_path / "registry.json"
    path.write_text(json.dumps(_registry(candidate)), encoding="utf-8")
    snapshots, errors = load_registry_snapshots(path)
    assert snapshots == {}
    assert errors == []


def test_valid_snapshot_is_normalized_and_revision_is_optional():
    parsed = parse_source_snapshot(_snapshot(), source_id="source-1")
    assert parsed.sha256 == "a" * 64
    assert parsed.artifact_kind == "pdf"
    assert parsed.revision_label == "Published Apr 23, 2026"

    no_revision = _snapshot()
    no_revision["revision_label"] = None
    parsed_null = parse_source_snapshot(no_revision, source_id="source-1")
    assert parsed_null.revision_label is None
    assert parsed_null.to_dict()["revision_label"] is None


def test_snapshot_loader_accepts_utf8_bom(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        "\ufeff" + json.dumps(_registry(_source(snapshot=_snapshot()))),
        encoding="utf-8",
    )
    snapshots, errors = load_registry_snapshots(path)
    assert errors == []
    assert snapshots["source-1"].sha256 == "a" * 64


def test_bad_snapshot_hash_and_timestamp_are_rejected(tmp_path):
    bad = _snapshot()
    bad["sha256"] = "not-a-hash"
    bad["retrieved_at"] = "yesterday"
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(_registry(_source(snapshot=bad))),
        encoding="utf-8",
    )
    _, errors = load_registry_snapshots(path)
    assert errors
    assert any("retrieved_at" in item or "sha256" in item for item in errors)


def test_snapshot_set_fingerprint_changes_when_artifact_changes():
    first = parse_source_snapshot(_snapshot(), source_id="source-1")
    second_payload = _snapshot()
    second_payload["sha256"] = "b" * 64
    second = parse_source_snapshot(second_payload, source_id="source-1")
    assert snapshot_set_sha256({"source-1": first}) != snapshot_set_sha256({"source-1": second})


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
