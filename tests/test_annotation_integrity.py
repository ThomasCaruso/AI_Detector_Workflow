import json

from authorship_shift.annotation_integrity import (
    build_frozen_manifest,
    verify_frozen_manifest,
    write_frozen_manifest,
)


def _packet(packet_id="a"):
    return {
        "id": packet_id,
        "genre": "science_summary",
        "split": "train",
        "instruction": "Explain the observation.",
        "content_atoms": [],
        "immutable_details": [],
        "required_qualifications": [],
        "target_text": "A human target paragraph that remains frozen during annotation.",
        "provenance": {
            "kind": "public_domain",
            "source_id": "source-1",
            "license": "Public Domain (U.S. Government work)",
            "note": "reviewed",
        },
        "metadata": {"annotation_status": "pending"},
    }


def test_semantic_fields_do_not_change_frozen_fingerprint(tmp_path):
    packet = _packet()
    manifest = build_frozen_manifest([packet])
    original = manifest["packets"]["a"]

    packet["content_atoms"] = ["human paragraph", "annotation remains separate"]
    packet["required_qualifications"] = ["do not change frozen source fields"]
    packet["metadata"]["annotation_status"] = "ready"
    assert build_frozen_manifest([packet])["packets"]["a"] == original


def test_target_instruction_split_and_provenance_are_frozen(tmp_path):
    for field, replacement in [
        ("target_text", "Modified target"),
        ("instruction", "Modified instruction"),
        ("split", "holdout"),
        (
            "provenance",
            {"kind": "user_owned", "source_id": "other", "license": None, "note": "changed"},
        ),
    ]:
        root = tmp_path / field
        root.mkdir()
        packet = _packet()
        (root / "a.json").write_text(json.dumps(packet), encoding="utf-8")
        write_frozen_manifest([packet], root)

        changed = json.loads((root / "a.json").read_text(encoding="utf-8"))
        changed[field] = replacement
        (root / "a.json").write_text(json.dumps(changed), encoding="utf-8")

        errors = verify_frozen_manifest(root)
        assert any("frozen source-target fields changed" in error for error in errors)


def test_new_or_missing_packet_is_rejected(tmp_path):
    packet = _packet()
    (tmp_path / "a.json").write_text(json.dumps(packet), encoding="utf-8")
    write_frozen_manifest([packet], tmp_path)

    extra = _packet("b")
    (tmp_path / "b.json").write_text(json.dumps(extra), encoding="utf-8")
    errors = verify_frozen_manifest(tmp_path)
    assert any("absent from frozen manifest" in error for error in errors)

    (tmp_path / "a.json").unlink()
    errors = verify_frozen_manifest(tmp_path)
    assert any("listed in frozen manifest is missing" in error for error in errors)
