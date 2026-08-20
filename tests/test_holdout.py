import json

from authorship_shift.holdout import prepare_holdout_lock, verify_holdout_lock
from authorship_shift.models import read_json


def test_holdout_lock_binds_split_decision_and_sample_hashes(tmp_path):
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

    lock_path = prepare_holdout_lock(
        corpus,
        development_suite,
        tmp_path / "holdout",
        split_file=split,
        slots=2,
    )
    lock = read_json(lock_path)
    assert lock["selected_variants"] == ["baseline", "full"]
    assert lock["sample_count"] == 1
    assert verify_holdout_lock(lock_path)["ok"] is True

    held.write_text("changed after lock", encoding="utf-8")
    verification = verify_holdout_lock(lock_path)
    assert verification["ok"] is False
    assert any("holdout sample changed" in error for error in verification["errors"])
