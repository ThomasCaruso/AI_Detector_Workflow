from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable
import time

from .ablation import run_ablation_suite
from .confidence import write_confidence_report
from .models import read_json, write_json
from .provenance import canonical_json_sha256, sha256_file
from .providers.base import Provider


def _resolve_entry(corpus_root: Path, entry: str) -> Path:
    raw = Path(entry)
    candidates = (raw, corpus_root / raw, corpus_root / raw.name)
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()
    raise FileNotFoundError(f"Holdout split entry cannot be resolved: {entry}")


def _selected_variants(decision: dict[str, Any], slots: int) -> list[str]:
    names = [str(row.get("variant", "")) for row in decision.get("recommended_validation_slots", []) if row.get("variant")]
    names = list(dict.fromkeys(names))
    if "baseline" not in names:
        names.insert(0, "baseline")
    if slots < 1:
        raise ValueError("slots must be at least 1")
    return names[:slots]


def _partition_payload(lock: dict[str, Any]) -> dict[str, Any]:
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


def _directory_has_payload(path: Path) -> bool:
    return path.exists() and any(path.iterdir())


def prepare_holdout_lock(
    corpus_dir: str | Path,
    development_suite: str | Path,
    output_dir: str | Path,
    *,
    split_file: str | Path,
    slots: int = 3,
    variants: str | Iterable[str] | None = None,
) -> Path:
    corpus_root = Path(corpus_dir).resolve()
    development_root = Path(development_suite).resolve()
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)
    lock_path = output_root / "holdout_lock.json"
    if lock_path.exists():
        raise FileExistsError(f"Holdout lock already exists: {lock_path}")
    if _directory_has_payload(output_root / "suite"):
        raise FileExistsError(
            f"Holdout suite directory already contains data: {output_root / 'suite'}. "
            "Use a fresh output directory for a new lock."
        )

    split_path = Path(split_file).resolve()
    split = read_json(split_path)
    holdout_entries = list(split.get("holdout", []))
    if not holdout_entries:
        raise ValueError("Split contains no holdout samples")

    decision_path = development_root / "decision.json"
    decision_hash = None
    if variants is None:
        if not decision_path.exists():
            raise FileNotFoundError("decision.json is required unless --variants is supplied explicitly")
        decision = read_json(decision_path)
        selected = _selected_variants(decision, slots)
        decision_hash = sha256_file(decision_path)
    elif isinstance(variants, str):
        selected = [v.strip() for v in variants.split(",") if v.strip()]
    else:
        selected = [str(v).strip() for v in variants if str(v).strip()]
    selected = list(dict.fromkeys(selected))
    if not selected:
        raise ValueError("At least one holdout variant is required")
    if "baseline" not in selected:
        selected.insert(0, "baseline")

    samples = []
    for entry in holdout_entries:
        path = _resolve_entry(corpus_root, str(entry))
        samples.append({
            "path": str(path),
            "sha256": sha256_file(path),
        })

    payload: dict[str, Any] = {
        "schema_version": 2,
        "created_at": time.time(),
        "corpus_root": str(corpus_root),
        "development_suite": str(development_root),
        "split_file": str(split_path),
        "split_sha256": sha256_file(split_path),
        "decision_file": str(decision_path) if decision_path.exists() else None,
        "decision_sha256": decision_hash,
        "selected_variants": selected,
        "sample_count": len(samples),
        "samples": samples,
        "external_detector_queries_allowed": 0,
    }
    partition = _partition_payload(payload)
    payload["partition_sha256"] = canonical_json_sha256(partition)
    payload["lock_fingerprint"] = canonical_json_sha256({k: v for k, v in payload.items() if k != "created_at"})
    write_json(lock_path, payload)
    write_json(output_root / "holdout_partition.json", partition)
    return lock_path


def verify_holdout_lock(lock_path: str | Path) -> dict[str, Any]:
    path = Path(lock_path)
    lock = read_json(path)
    errors: list[str] = []
    split_path = Path(str(lock.get("split_file", "")))
    if not split_path.exists():
        errors.append("source split file is missing")
    elif sha256_file(split_path) != lock.get("split_sha256"):
        errors.append("source split file changed after holdout lock")

    decision_file = lock.get("decision_file")
    decision_hash = lock.get("decision_sha256")
    if decision_file and decision_hash:
        decision_path = Path(str(decision_file))
        if not decision_path.exists():
            errors.append("source decision file is missing")
        elif sha256_file(decision_path) != decision_hash:
            errors.append("development decision changed after holdout lock")

    for sample in lock.get("samples", []):
        sample_path = Path(str(sample.get("path", "")))
        if not sample_path.exists():
            errors.append(f"holdout sample missing: {sample_path}")
        elif sha256_file(sample_path) != sample.get("sha256"):
            errors.append(f"holdout sample changed after lock: {sample_path}")

    expected_partition = _partition_payload(lock)
    expected_partition_hash = canonical_json_sha256(expected_partition)
    recorded_partition_hash = lock.get("partition_sha256")
    if recorded_partition_hash and expected_partition_hash != recorded_partition_hash:
        errors.append("locked partition metadata hash mismatch")
    partition_path = path.parent / "holdout_partition.json"
    if not partition_path.exists():
        errors.append("holdout_partition.json is missing")
    else:
        actual_partition = read_json(partition_path)
        if canonical_json_sha256(actual_partition) != expected_partition_hash:
            errors.append("holdout_partition.json changed after lock")

    expected_fingerprint = canonical_json_sha256({k: v for k, v in lock.items() if k not in {"created_at", "lock_fingerprint"}})
    if expected_fingerprint != lock.get("lock_fingerprint"):
        errors.append("holdout lock metadata fingerprint mismatch")

    return {
        "ok": not errors,
        "errors": errors,
        "lock": str(path),
        "sample_count": len(lock.get("samples", [])),
        "selected_variants": list(lock.get("selected_variants", [])),
        "lock_fingerprint": lock.get("lock_fingerprint"),
        "partition_sha256": expected_partition_hash,
    }


def run_holdout_validation(
    lock_path: str | Path,
    providers: Provider | list[Provider],
    *,
    judge_provider: Provider | None = None,
    base_config: dict[str, Any] | None = None,
    max_runs: int | None = None,
    resume: bool = True,
) -> dict[str, Any]:
    lock_path = Path(lock_path)
    verification = verify_holdout_lock(lock_path)
    if not verification["ok"]:
        raise RuntimeError("Holdout lock verification failed: " + "; ".join(verification["errors"]))
    lock = read_json(lock_path)
    root = lock_path.parent

    # Reconstruct the execution partition from the lock immediately before use.
    # This prevents an editable helper file from becoming a hidden source of validation drift.
    partition_path = root / "holdout_partition.json"
    write_json(partition_path, _partition_payload(lock))

    config = deepcopy(base_config or {})
    config.setdefault("external_evaluation", {})
    config["external_evaluation"]["development_queries_allowed"] = 0
    config["external_evaluation"]["milestone_queries_budget"] = 0
    config["holdout_validation"] = {
        "lock_fingerprint": lock["lock_fingerprint"],
        "source_split_sha256": lock["split_sha256"],
        "partition_sha256": verification["partition_sha256"],
        "selected_variants": lock["selected_variants"],
    }
    suite_root = root / "suite"
    result = run_ablation_suite(
        lock["corpus_root"],
        suite_root,
        providers,
        judge_provider=judge_provider,
        base_config=config,
        variants=lock["selected_variants"],
        split_file=partition_path,
        max_samples=None,
        max_runs=max_runs,
        resume=resume,
    )
    state = {
        "updated_at": time.time(),
        "lock_fingerprint": lock["lock_fingerprint"],
        "partition_sha256": verification["partition_sha256"],
        "planned_runs": result["planned_runs"],
        "completed_runs": result["completed_runs"],
        "complete": result["completed_runs"] >= result["planned_runs"],
        "external_detector_queries_used": 0,
    }
    write_json(root / "holdout_state.json", state)
    if state["complete"] and "baseline" in lock["selected_variants"] and len(lock["selected_variants"]) > 1:
        write_confidence_report(suite_root, baseline="baseline")
    return state
