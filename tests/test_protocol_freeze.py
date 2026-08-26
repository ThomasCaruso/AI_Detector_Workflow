"""Tests for frozen-protocol binding and digest verification.

Every artifact here is synthetic: files written into tmp_path with invented
digests and binding values. No corpus document, no protocol from a real
experiment, and no user prose.
"""

from __future__ import annotations

import json

from authorship_shift.protocol_freeze import (
    PROTOCOL_FREEZE_SCHEMA_VERSION,
    FrozenArtifact,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    verify_binding_consistency,
    verify_freeze,
    verify_recorded_digests,
)

DATA_DIGEST = "a" * 64
OTHER_DIGEST = "b" * 64


def _write(tmp_path, name: str, payload: dict) -> tuple[str, str]:
    path = tmp_path / name
    body = canonical_json_bytes(payload)
    path.write_bytes(body)
    return str(path), sha256_bytes(body)


def _artifact(tmp_path, name, bindings, payload=None):
    path, digest = _write(tmp_path, f"{name}.json", payload or {"name": name})
    return FrozenArtifact(name=name, path=path, sha256=digest, bindings=bindings)


def test_consistent_artifacts_pass(tmp_path):
    artifacts = [
        _artifact(tmp_path, "config", {"train_sha256": DATA_DIGEST, "experiment_id": "x"}),
        _artifact(tmp_path, "protocol", {"train_sha256": DATA_DIGEST, "experiment_id": "x"}),
    ]

    report = verify_freeze(artifacts, required_keys=["train_sha256", "experiment_id"])

    assert report.passed
    assert report.findings == ()


def test_disagreeing_binding_is_fatal(tmp_path):
    artifacts = [
        _artifact(tmp_path, "config", {"train_sha256": DATA_DIGEST}),
        _artifact(tmp_path, "protocol", {"train_sha256": OTHER_DIGEST}),
    ]

    report = verify_binding_consistency(artifacts, required_keys=["train_sha256"])

    assert not report.passed
    assert [f.check for f in report.findings] == ["binding_disagreement"]
    assert "train_sha256" in report.findings[0].detail


def test_missing_required_binding_is_reported(tmp_path):
    artifacts = [
        _artifact(tmp_path, "config", {"train_sha256": DATA_DIGEST}),
        _artifact(tmp_path, "protocol", {}),
    ]

    report = verify_binding_consistency(artifacts, required_keys=["train_sha256"])

    assert not report.passed
    assert report.findings[0].check == "missing_required_binding"
    assert "protocol" in report.findings[0].detail


def test_exemption_removes_the_obligation_to_declare(tmp_path):
    artifacts = [
        _artifact(tmp_path, "root", {"train_sha256": DATA_DIGEST}),
        _artifact(tmp_path, "leaf", {"train_sha256": DATA_DIGEST, "root_sha256": OTHER_DIGEST}),
    ]

    report = verify_binding_consistency(
        artifacts,
        required_keys=["train_sha256", "root_sha256"],
        exempt={"root": ["root_sha256"]},
    )

    assert report.passed


def test_exemption_does_not_excuse_a_wrong_value(tmp_path):
    """An exempt artifact that declares the key anyway is still checked."""

    artifacts = [
        _artifact(tmp_path, "root", {"root_sha256": DATA_DIGEST}),
        _artifact(tmp_path, "leaf", {"root_sha256": OTHER_DIGEST}),
    ]

    report = verify_binding_consistency(
        artifacts, required_keys=["root_sha256"], exempt={"root": ["root_sha256"]}
    )

    assert not report.passed
    assert report.findings[0].check == "binding_disagreement"


def test_digest_mismatch_is_detected(tmp_path):
    path, digest = _write(tmp_path, "config.json", {"a": 1})
    artifact = FrozenArtifact(name="config", path=path, sha256=digest, bindings={})
    assert verify_recorded_digests([artifact]).passed

    (tmp_path / "config.json").write_bytes(canonical_json_bytes({"a": 2}))
    report = verify_recorded_digests([artifact])

    assert not report.passed
    assert report.findings[0].check == "digest_mismatch"


def test_unreadable_artifact_is_reported(tmp_path):
    artifact = FrozenArtifact(
        name="ghost", path=str(tmp_path / "absent.json"), sha256=DATA_DIGEST, bindings={}
    )

    report = verify_recorded_digests([artifact])

    assert not report.passed
    assert report.findings[0].check == "artifact_unreadable"


def test_duplicate_artifact_names_are_reported(tmp_path):
    a = _artifact(tmp_path, "same", {"k": "v"})
    b = FrozenArtifact(name="same", path=a.path, sha256=a.sha256, bindings={"k": "v"})

    report = verify_binding_consistency([a, b], required_keys=["k"])

    assert not report.passed
    assert any(f.check == "duplicate_artifact_name" for f in report.findings)


def test_verify_freeze_merges_both_check_families(tmp_path):
    path, digest = _write(tmp_path, "one.json", {"a": 1})
    good = FrozenArtifact(name="one", path=path, sha256=digest, bindings={"k": "v"})
    bad = FrozenArtifact(name="two", path=path, sha256=OTHER_DIGEST, bindings={"k": "w"})

    report = verify_freeze([good, bad], required_keys=["k"])

    checks = {f.check for f in report.findings}
    assert "binding_disagreement" in checks
    assert "digest_mismatch" in checks
    assert not report.passed


def test_canonical_json_bytes_is_order_independent():
    left = canonical_json_bytes({"b": 2, "a": 1})
    right = canonical_json_bytes({"a": 1, "b": 2})

    assert left == right
    assert left.endswith(b"\n")


def test_canonical_json_bytes_changes_with_content():
    assert canonical_json_bytes({"a": 1}) != canonical_json_bytes({"a": 2})


def test_sha256_file_matches_sha256_bytes(tmp_path):
    path = tmp_path / "x.bin"
    payload = b"synthetic payload"
    path.write_bytes(payload)

    assert sha256_file(str(path)) == sha256_bytes(payload)


def test_artifact_as_dict_round_trips():
    artifact = FrozenArtifact(
        name="config", path="p.json", sha256=DATA_DIGEST, bindings={"k": "v"}
    )

    payload = artifact.as_dict()

    assert json.loads(json.dumps(payload)) == payload
    assert payload["bindings"] == {"k": "v"}


def test_nested_binding_values_compare_structurally(tmp_path):
    a = _artifact(tmp_path, "a", {"versions": {"x": "1", "y": "2"}})
    b = _artifact(tmp_path, "b", {"versions": {"y": "2", "x": "1"}})

    report = verify_binding_consistency(a and [a, b], required_keys=["versions"])

    assert report.passed


def test_schema_version_is_pinned():
    assert PROTOCOL_FREEZE_SCHEMA_VERSION == 1
