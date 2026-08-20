from pathlib import Path
from authorship_shift.corpus import deterministic_split


def test_split_is_deterministic():
    files = [Path(f"sample_{i}.txt") for i in range(20)]
    a = deterministic_split(files, seed="x")
    b = deterministic_split(files, seed="x")
    assert a == b
    assert len(a["development"]) + len(a["holdout"]) == 20
