from pathlib import Path
from authorship_shift.corpus import deterministic_split


def test_split_is_deterministic():
    files = [Path(f"sample_{i}.txt") for i in range(20)]
    a = deterministic_split(files, seed="x")
    b = deterministic_split(files, seed="x")
    assert a == b
    assert len(a["development"]) + len(a["holdout"]) == 20


def test_split_uses_relative_paths_not_only_basenames(tmp_path):
    business = tmp_path / "business"; business.mkdir()
    science = tmp_path / "science"; science.mkdir()
    a = business / "sample.txt"; b = science / "sample.txt"
    a.write_text("business", encoding="utf-8")
    b.write_text("science", encoding="utf-8")

    split = deterministic_split(
        [a, b],
        holdout_fraction=0.5,
        seed="s3",
        base_dir=tmp_path,
    )

    assert split["holdout"] == ["business/sample.txt"]
    assert split["development"] == ["science/sample.txt"]
    assert not any(str(tmp_path) in entry for values in split.values() for entry in values)
