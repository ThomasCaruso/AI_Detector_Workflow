from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json


def deterministic_split(files: list[Path], *, holdout_fraction: float = 0.2, seed: str = "authorship-shift") -> dict[str, list[str]]:
    if not 0 < holdout_fraction < 1:
        raise ValueError("holdout_fraction must be between 0 and 1")
    train: list[str] = []
    holdout: list[str] = []
    cutoff = int(holdout_fraction * 10_000)
    for path in sorted(files, key=lambda p: str(p)):
        digest = sha256(f"{seed}:{path.name}".encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 10_000
        (holdout if bucket < cutoff else train).append(str(path))
    return {"development": train, "holdout": holdout}


def split_directory(directory: str | Path, *, holdout_fraction: float = 0.2, seed: str = "authorship-shift", output: str | Path | None = None) -> Path:
    root = Path(directory)
    files = [p for p in root.rglob("*.txt") if p.is_file()]
    result = deterministic_split(files, holdout_fraction=holdout_fraction, seed=seed)
    out = Path(output) if output else root / "split.json"
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return out
