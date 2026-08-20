import json
from pathlib import Path
import shutil

from authorship_shift.holdout import prepare_holdout_lock, verify_holdout_lock
from authorship_shift.models import read_json
from authorship_shift.provenance import canonical_json_sha256


def _fixture(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    dev = corpus / "dev.txt"
    held = corpus / "held.txt"
    dev.write_text("development sample " * 30, encoding="utf-8")
    held.write_text("held out sample " * 30, encoding="utf-8")

    split = corpus / "split.json"
    split.write_text(json.dumps({"development": ["dev.txt"], "holdout": ["held.txt"]}), encoding="utf-8")

    development_suite = tmp_path / "development_suite"
    development_suite.mkdir()
    (development_suite / "decision.json").write_text(json.dumps({
        "recommended_validation_slots": [
            {"variant": "baseline"},
            {"variant": "full"},
        ]
    }), encoding="utf-8")
    return corpus, dev, held, split, development_suite


def _partition_payload(lock):
    return {
        "development": [str(sample["path"]) for sample in lock.get("samples", [])],
        "holdout": [],
        "metadata": {
            "method": "locked_holdout_rebound_as_validation_partition",
            "source_split": str(lock.get("split_file", "")),
            "source_split_sha256": lock.get("split_sha256"),
            "sample_hashes": {str(sample["path"]): sample.get("sha256") for sample in lock.get("samples", [])},
        },
    }


def test_holdout_lock_binds_split_decision_and_sample_hashes(tmp_path):
    corpus, _, held, split, development_suite = _fixture(tmp_path)
    lock_path = prepare_holdout_lock(
        corpus,
        development_suite,
        tmp_path / "holdout",
        split_file=split,
        slots=2,
    )
    lock = read_json(lock_path)
    assert lock["schema_version"] == 3
    assert lock["path_mode"] == "portable_relative"
    assert lock["selected_variants"] == ["baseline", "full"]
    assert lock["sample_count"] == 1
    assert lock["samples"][0]["path"] == "held.txt"
    assert not Path(lock["corpus_root"]).is_absolute()
    assert not Path(lock["split_file"]).is_absolute()
    assert lock["partition_sha256"]
    assert verify_holdout_lock(lock_path)["ok"] is True

    held.write_text("changed after lock", encoding="utf-8")
    verification = verify_holdout_lock(lock_path)
    assert verification["ok"] is False
    assert any("holdout sample changed" in error for error in verification["errors"])


def test_holdout_lock_survives_project_relocation(tmp_path):
    original = tmp_path / "original"
    original.mkdir()
    corpus, _, _, split, development_suite = _fixture(original)
    lock_path = prepare_holdout_lock(
        corpus,
        development_suite,
        original / "holdout",
        split_file=split,
        slots=2,
    )
    original_fingerprint = read_json(lock_path)["lock_fingerprint"]

    moved = tmp_path / "moved"
    shutil.copytree(original, moved)
    shutil.rmtree(original)

    moved_lock = moved / "holdout" / "holdout_lock.json"
    verification = verify_holdout_lock(moved_lock)
    assert verification["ok"] is True
    assert verification["lock_fingerprint"] == original_fingerprint


def test_legacy_absolute_v2_lock_still_verifies(tmp_path):
    corpus, _, _, split, development_suite = _fixture(tmp_path)
    output = tmp_path / "holdout"
    lock_path = prepare_holdout_lock(
        corpus,
        development_suite,
        output,
        split_file=split,
        slots=2,
    )
    lock = read_json(lock_path)
    base = lock_path.parent
    corpus_root = (base / lock["corpus_root"]).resolve()

    lock["schema_version"] = 2
    lock.pop("path_mode", None)
    lock["corpus_root"] = str(corpus_root)
    lock["development_suite"] = str((base / lock["development_suite"]).resolve())
    lock["split_file"] = str((base / lock["split_file"]).resolve())
    if lock.get("decision_file"):
        lock["decision_file"] = str((base / lock["decision_file"]).resolve())
    for sample in lock["samples"]:
        sample["path"] = str((corpus_root / sample["path"]).resolve())

    partition = _partition_payload(lock)
    lock["partition_sha256"] = canonical_json_sha256(partition)
    lock["lock_fingerprint"] = canonical_json_sha256({
        key: value for key, value in lock.items() if key not in {"created_at", "lock_fingerprint"}
    })
    lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")
    (output / "holdout_partition.json").write_text(json.dumps(partition, indent=2), encoding="utf-8")

    assert verify_holdout_lock(lock_path)["ok"] is True


def test_holdout_partition_tampering_is_detected(tmp_path):
    corpus, _, _, split, development_suite = _fixture(tmp_path)
    output = tmp_path / "holdout"
    lock_path = prepare_holdout_lock(
        corpus,
        development_suite,
        output,
        split_file=split,
        slots=2,
    )
    partition = output / "holdout_partition.json"
    partition.write_text(json.dumps({"development": [], "holdout": ["not-locked.txt"]}), encoding="utf-8")
    verification = verify_holdout_lock(lock_path)
    assert verification["ok"] is False
    assert any("holdout_partition.json changed" in error for error in verification["errors"])


def test_prepare_refuses_stale_suite_directory(tmp_path):
    corpus, _, _, split, development_suite = _fixture(tmp_path)
    output = tmp_path / "holdout"
    suite = output / "suite"
    suite.mkdir(parents=True)
    (suite / "stale.txt").write_text("old run", encoding="utf-8")

    try:
        prepare_holdout_lock(corpus, development_suite, output, split_file=split, slots=2)
    except FileExistsError as exc:
        assert "suite directory already contains data" in str(exc)
    else:
        assert False, "stale holdout suite should be rejected"
