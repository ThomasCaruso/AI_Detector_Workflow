import json

from authorship_shift.registry_io import load_source_registry_safe


def _candidate():
    return {
        "source_id": "source-1",
        "title": "Candidate",
        "genre": "business_analysis",
        "status": "candidate",
        "provenance_kind": "public_domain",
        "rights_basis": "",
    }


def test_safe_registry_loader_accepts_utf8_bom(tmp_path):
    path = tmp_path / "registry.json"
    payload = {"schema_version": 1, "sources": [_candidate()]}
    path.write_text("\ufeff" + json.dumps(payload), encoding="utf-8")

    rows, errors = load_source_registry_safe(path)
    assert errors == []
    assert [row.source_id for row in rows] == ["source-1"]


def test_safe_registry_loader_returns_record_validation_error(tmp_path):
    bad = _candidate()
    bad["status"] = "approved"
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps({"schema_version": 1, "sources": [bad]}),
        encoding="utf-8",
    )

    rows, errors = load_source_registry_safe(path)
    assert rows == []
    assert errors == ["source-1: approved sources require a rights_basis"]


def test_safe_registry_loader_returns_json_error_instead_of_raising(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text('{"schema_version": 1,', encoding="utf-8")

    rows, errors = load_source_registry_safe(path)
    assert rows == []
    assert errors
