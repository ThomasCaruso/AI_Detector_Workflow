from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import os

from .metrics import measure
from .provenance import sha256_file


def _portable_reference(base_dir: Path, target: Path) -> str:
    """Return a relocatable path when base and target share a filesystem."""
    base = base_dir.resolve()
    resolved = target.resolve()
    try:
        return Path(os.path.relpath(resolved, base)).as_posix()
    except ValueError:
        # Windows can raise when paths live on different drives. Preserve the
        # absolute path rather than producing an invalid reference.
        return str(resolved)


def deterministic_split(
    files: list[Path],
    *,
    holdout_fraction: float = 0.2,
    seed: str = "authorship-shift",
    base_dir: str | Path | None = None,
) -> dict[str, list[str]]:
    if not 0 < holdout_fraction < 1:
        raise ValueError("holdout_fraction must be between 0 and 1")
    root = Path(base_dir).resolve() if base_dir is not None else None
    train: list[str] = []
    holdout: list[str] = []
    cutoff = int(holdout_fraction * 10_000)
    keyed: list[tuple[str, Path]] = []
    for raw in files:
        path = Path(raw)
        ref = _portable_reference(root, path) if root is not None else path.as_posix()
        keyed.append((ref, path))
    for ref, _ in sorted(keyed, key=lambda item: item[0]):
        digest = sha256(f"{seed}:{ref}".encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) % 10_000
        (holdout if bucket < cutoff else train).append(ref)
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
    out = (Path(output) if output else root / "corpus_manifest.json").resolve()
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
        "root": _portable_reference(out.parent, root),
        "sample_count": len(entries),
        "entries": entries,
        "duplicate_hash_groups": duplicate_groups,
    }
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return out


def _stable_order(entries: list[dict[str, Any]], seed: str) -> list[dict[str, Any]]:
    return sorted(
        entries,
        key=lambda entry: sha256(f"{seed}:{entry['path']}".encode("utf-8")).hexdigest(),
    )


def _rebalance_nonempty_partitions(
    development: list[str],
    holdout: list[str],
    *,
    seed: str,
) -> tuple[list[str], list[str], dict[str, Any] | None]:
    """Guarantee both partitions are nonempty when the corpus has at least two samples.

    Singleton strata are hashed independently and can, in aggregate, land entirely on one
    side. This deterministic fallback prevents a nominal holdout split from silently having
    no holdout data.
    """
    total = len(development) + len(holdout)
    if total < 2 or (development and holdout):
        return development, holdout, None

    source = development if development else holdout
    destination_name = "holdout" if development else "development"
    ordered = sorted(source, key=lambda path: sha256(f"{seed}:rebalance:{path}".encode("utf-8")).hexdigest())
    moved = ordered[0]
    source.remove(moved)
    if destination_name == "holdout":
        holdout.append(moved)
    else:
        development.append(moved)
    return development, holdout, {
        "applied": True,
        "moved_path": moved,
        "destination": destination_name,
        "reason": "all singleton/hash-assigned samples landed in one partition",
    }


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

    development, holdout, rebalance = _rebalance_nonempty_partitions(development, holdout, seed=seed)
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
            "fallback_rebalance": rebalance,
        },
    }


def validate_manifest(manifest_path: str | Path) -> dict[str, Any]:
    path = Path(manifest_path).resolve()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    stored_root = Path(str(manifest.get("root") or "."))
    root = stored_root if stored_root.is_absolute() else (path.parent / stored_root).resolve()
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
    out = (Path(output) if output else root / "split.json").resolve()
    if stratify:
        manifest_file = (Path(manifest_path) if manifest_path else root / "corpus_manifest.json").resolve()
        if not manifest_file.exists():
            manifest_file = build_manifest(root, output=manifest_file)
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
        result = stratified_split(manifest, holdout_fraction=holdout_fraction, seed=seed)
        result["metadata"]["manifest"] = _portable_reference(out.parent, manifest_file)
        result["metadata"]["manifest_sha256"] = sha256_file(manifest_file)
    else:
        files = [p for p in root.rglob("*.txt") if p.is_file()]
        result = deterministic_split(files, holdout_fraction=holdout_fraction, seed=seed, base_dir=root)
    out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return out
