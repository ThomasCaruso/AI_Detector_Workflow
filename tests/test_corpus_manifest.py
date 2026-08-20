import json

from authorship_shift.corpus import build_manifest, stratified_split, validate_manifest


def test_manifest_and_stratified_split_preserve_genre_coverage(tmp_path):
    for genre in ("business", "science"):
        folder = tmp_path / genre
        folder.mkdir()
        for i in range(4):
            (folder / f"sample_{i}.txt").write_text((f"{genre} topic {i} " * 30).strip(), encoding="utf-8")

    manifest_path = build_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    split = stratified_split(manifest, holdout_fraction=0.25, seed="test")

    assert manifest["sample_count"] == 8
    assert len(split["development"]) == 6
    assert len(split["holdout"]) == 2
    assert not (set(split["development"]) & set(split["holdout"]))
    assert validate_manifest(manifest_path)["ok"] is True
