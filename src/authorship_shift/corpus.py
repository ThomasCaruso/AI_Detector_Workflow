from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any
import json

from .metrics import measure
from .provenance import sha256_file


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


def length_band(word_count: int) -> str:
    if word_count < 250:
        return "short"
    if word_count < 700:
        return "medium"
    return "long"


def _genre(root: Path, path: Path) -> str:
    rel = path.relative_to(root)
    return rel.parts[0] if len(rel.parts) > 1 else "unspecified"


def build_manifest(directory: str | Path, *, output: str | Path | None = None) -> Path:
    root = Path(directory).resolve()
    files = sorted(path for path in root.rglob("*.txt") if path.is_file())
    entries: list[dict[str, Any]] = []
    hashes: dict[str, list[str]] = defaultdict(list)
    for path in files:
        text = path.read_text(encoding="utf-8")
        metrics = measure(text)
        rel = path.relative_to(root).as_posix()
        digest = sha256_file(path)
        hashes[digest].append(rel)
        entries.append({
            "path": rel,
            "sha256": digest,
            "genre": _genre(root, path),
            "length_band": length_band(metrics.word_count),
            "word_count": metrics.word_count,
            "sentence_count": metrics.sentence_count,
            "paragraph_count": metrics.paragraph_count,
        })
    duplicate_groups = [paths for paths in hashes.values() if len(paths) > 1]
    manifest = {
        "schema_version": 1,
        "root": str(root),
        "sample_count": len(entries),
        "entries": entries,
        "duplicate_hash_groups": duplicate_groups,
    }
    out = Path(output) if output else root / "corpus_manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


def _stable_order(entries: list[dict[str, Any]], seed: str) -> list[dict[str, Any]]:
    return sorted(
        entries,
        key=lambda entry: sha256(f"{seed}:{entry['path']}".encode("utf-8")).hexdigest(),
    )


def stratified_split(
    manifest: dict[str, Any],
    *,
    holdout_fraction: float = 0.2,
    seed: str = "authorship-shift",
) -> dict[str, Any]:
    if not 0 < holdout_fraction < 1:
        raise ValueError("holdout_fraction must be between 0 and 1")
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in manifest.get("entries", []):
        grouped[(str(entry.get("genre", "unspecified")), str(entry.get("length_band", "unknown")))].append(entry)

    development: list[str] = []
    holdout: list[str] = []
    strata: list[dict[str, Any]] = []
    cutoff = int(holdout_fraction * 10_000)
    for (genre, band), entries in sorted(grouped.items()):
        ordered = _stable_order(entries, f"{seed}:{genre}:{band}")
        n = len(ordered)
        if n >= 2:
            holdout_n = round(n * holdout_fraction)
            holdout_n = min(n - 1, max(1, holdout_n))
            h = ordered[:holdout_n]
            d = ordered[holdout_n:]
        else:
            entry = ordered[0]
            bucket = int(sha256(f"{seed}:{entry['path']}".encode("utf-8")).hexdigest()[:8], 16) % 10_000
            h, d = ([entry], []) if bucket < cutoff else ([], [entry])
        holdout.extend(entry["path"] for entry in h)
        development.extend(entry["path"] for entry in d)
        strata.append({
            "genre": genre,
            "length_band": band,
            "samples": n,
            "development": len(d),
            "holdout": len(h),
        })

    overlap = set(development) & set(holdout)
    if overlap:
        raise RuntimeError(f"Split overlap detected: {sorted(overlap)}")
    return {
        "development": sorted(development),
        "holdout": sorted(holdout),
        "metadata": {
            "method": "genre_length_stratified",
            "holdout_fraction": holdout_fraction,
            "seed": seed,
            "strata": strata,
        },
    }


def validate_manifest(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path)
    manifest = json.loads(path.read_text(encoding="utf-8"))
    root = Path(manifest.get("root") or path.parent)
    errors: list[str] = []
    warnings: list[str] = []
    seen_paths: set[str] = set()
    for entry in manifest.get("entries", []):
        rel = str(entry.get("path", ""))
        if not rel:
            errors.append("manifest entry has no path")
            continue
        if rel in seen_paths:
            errors.append(f"duplicate manifest path: {rel}")
        seen_paths.add(rel)
        file_path = root / rel
        if not file_path.exists():
            errors.append(f"missing corpus file: {rel}")
            continue
        if sha256_file(file_path) != entry.get("sha256"):
            errors.append(f"hash mismatch: {rel}")
        if int(entry.get("word_count", 0) or 0) < 50:
            warnings.append(f"very short sample (<50 words): {rel}")
    for group in manifest.get("duplicate_hash_groups", []):
        warnings.append("exact duplicate content: " + ", ".join(group))
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "sample_count": len(manifest.get("entries", [])),
        "manifest": str(path),
    }


def split_directory(
    directory: str | Path,
    *,
    holdout_fraction: float = 0.2,
    seed: str = "authorship-shift",
    output: str | Path | None = None,
    stratify: bool = False,
    manifest_path: str | Path | None = None,
) -> Path:
    root = Path(directory).resolve()
    out = Path(output) if output else root / "split.json"
    if stratify:
        manifest_file = Path(manifest_path) if manifest_path else root / "corpus_manifest.json"
        if not manifest_file.exists():
            manifest_file = build_manifest(root, output=manifest_file)
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        result = stratified_split(manifest, holdout_fraction=holdout_fraction, seed=seed)
        result["metadata"]["manifest"] = str(manifest_file)
        result["metadata"]["manifest_sha256"] = sha256_file(manifest_file)
    else:
        files = [p for p in root.rglob("*.txt") if p.is_file()]
        result = deterministic_split(files, holdout_fraction=holdout_fraction, seed=seed)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return out
