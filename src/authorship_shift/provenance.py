from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any
import json


def sha256_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(payload)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_experiment(root: str | Path) -> dict[str, Any]:
    root = Path(root)
    errors: list[str] = []
    warnings: list[str] = []
    if not (root / "manifest.json").exists():
        return {"root": str(root), "ok": False, "errors": ["manifest.json is missing"], "warnings": []}

    manifest = _read_json(root / "manifest.json")
    config = _read_json(root / "config.json") if (root / "config.json").exists() else None
    source_path = root / "source.txt"

    if not source_path.exists():
        errors.append("source.txt is missing")
    elif manifest.get("source_sha256"):
        actual = sha256_file(source_path)
        if actual != manifest["source_sha256"]:
            errors.append("source.txt hash does not match manifest source_sha256")
    else:
        warnings.append("manifest has no source_sha256 (legacy experiment)")

    if config is None:
        errors.append("config.json is missing")
    elif manifest.get("config_sha256"):
        if canonical_json_sha256(config) != manifest["config_sha256"]:
            errors.append("config.json hash does not match manifest config_sha256")
    else:
        warnings.append("manifest has no config_sha256 (legacy experiment)")

    candidate_ids = list(manifest.get("candidate_ids", []))
    candidate_hashes: dict[str, str] = {}
    for candidate_id in candidate_ids:
        path = root / "candidates" / f"{candidate_id}.json"
        if not path.exists():
            errors.append(f"candidate file missing: {candidate_id}")
            continue
        candidate = _read_json(path)
        text = str(candidate.get("text", ""))
        actual_hash = sha256_text(text)
        candidate_hashes[candidate_id] = actual_hash
        recorded = (candidate.get("metadata") or {}).get("content_sha256")
        if recorded and recorded != actual_hash:
            errors.append(f"candidate content hash mismatch: {candidate_id}")
        elif not recorded:
            warnings.append(f"candidate lacks content_sha256: {candidate_id}")

    frozen_ids = list(manifest.get("frozen_candidate_ids", []))
    for candidate_id in frozen_ids:
        frozen_path = root / "frozen" / f"{candidate_id}.txt"
        if candidate_id not in candidate_hashes:
            errors.append(f"frozen candidate not present in candidate_ids: {candidate_id}")
            continue
        if not frozen_path.exists():
            errors.append(f"frozen text missing: {candidate_id}")
            continue
        frozen_hash = sha256_file(frozen_path)
        if frozen_hash != candidate_hashes[candidate_id]:
            errors.append(f"frozen text differs from candidate content: {candidate_id}")
        candidate = _read_json(root / "candidates" / f"{candidate_id}.json")
        recorded = (candidate.get("metadata") or {}).get("frozen_sha256")
        if recorded and recorded != frozen_hash:
            errors.append(f"frozen_sha256 metadata mismatch: {candidate_id}")
        elif not recorded:
            warnings.append(f"frozen candidate lacks frozen_sha256: {candidate_id}")

    external_files = sorted((root / "external").glob("*.json")) if (root / "external").exists() else []
    used = int(manifest.get("external_queries_used", 0))
    if used != len(external_files):
        errors.append(f"external query count mismatch: manifest={used}, files={len(external_files)}")
    for path in external_files:
        result = _read_json(path)
        candidate_id = result.get("candidate_id")
        if candidate_id and candidate_id not in candidate_hashes:
            errors.append(f"external result references unknown candidate: {candidate_id}")
        if candidate_id and result.get("candidate_sha256"):
            if result["candidate_sha256"] != candidate_hashes.get(candidate_id):
                errors.append(f"external result candidate hash mismatch: {path.name}")
        elif candidate_id:
            warnings.append(f"external result lacks candidate_sha256: {path.name}")

    fingerprint = canonical_json_sha256({
        "source_sha256": sha256_file(source_path) if source_path.exists() else None,
        "config_sha256": canonical_json_sha256(config) if config is not None else None,
        "candidate_hashes": candidate_hashes,
        "frozen_ids": frozen_ids,
        "external_files": [sha256_file(path) for path in external_files],
    })
    return {
        "root": str(root),
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "candidate_count": len(candidate_ids),
        "frozen_count": len(frozen_ids),
        "external_result_count": len(external_files),
        "fingerprint": fingerprint,
    }


def audit_suite(suite_dir: str | Path) -> dict[str, Any]:
    root = Path(suite_dir)
    results_path = root / "suite_results.json"
    if not results_path.exists():
        raise FileNotFoundError(f"Missing suite_results.json under {root}")
    payload = _read_json(results_path)
    runs = list(payload.get("runs", []))
    audits: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in runs:
        experiment_root = str(row.get("experiment_root", ""))
        if not experiment_root or experiment_root in seen:
            continue
        seen.add(experiment_root)
        audit = audit_experiment(experiment_root)
        if audit.get("external_result_count", 0):
            audit.setdefault("errors", []).append("ablation run contains external detector results")
            audit["ok"] = False
        audits.append(audit)
    missing_roots = [str(row.get("experiment_root", "")) for row in runs if row.get("experiment_root") and not Path(str(row["experiment_root"])).exists()]
    errors = sum(len(a.get("errors", [])) for a in audits)
    warnings = sum(len(a.get("warnings", [])) for a in audits)
    return {
        "suite_dir": str(root),
        "run_records": len(runs),
        "audited_experiments": len(audits),
        "ok": errors == 0 and not missing_roots,
        "error_count": errors + len(missing_roots),
        "warning_count": warnings,
        "missing_experiment_roots": missing_roots,
        "experiments": audits,
        "suite_results_sha256": sha256_file(results_path),
    }


def write_integrity_report(target: str | Path, output: str | Path | None = None, *, suite: bool = False) -> Path:
    target = Path(target)
    report = audit_suite(target) if suite else audit_experiment(target)
    path = Path(output) if output else target / "integrity_report.md"
    lines = ["# Integrity Report", "", f"Status: **{'PASS' if report['ok'] else 'FAIL'}**", ""]
    if suite:
        lines += [
            f"Run records: {report['run_records']}",
            f"Audited experiments: {report['audited_experiments']}",
            f"Errors: {report['error_count']}",
            f"Warnings: {report['warning_count']}",
            f"Suite results SHA-256: `{report['suite_results_sha256']}`",
            "",
        ]
        for audit in report["experiments"]:
            lines.append(f"## {audit['root']}")
            lines.append("")
            lines.append(f"Fingerprint: `{audit['fingerprint']}`")
            for error in audit["errors"]:
                lines.append(f"- ERROR: {error}")
            for warning in audit["warnings"]:
                lines.append(f"- WARNING: {warning}")
            if not audit["errors"] and not audit["warnings"]:
                lines.append("- No integrity issues found.")
            lines.append("")
    else:
        lines += [
            f"Experiment fingerprint: `{report.get('fingerprint', '')}`",
            f"Candidates: {report.get('candidate_count', 0)}",
            f"Frozen candidates: {report.get('frozen_count', 0)}",
            f"External results: {report.get('external_result_count', 0)}",
            "",
        ]
        for error in report.get("errors", []):
            lines.append(f"- ERROR: {error}")
        for warning in report.get("warnings", []):
            lines.append(f"- WARNING: {warning}")
        if not report.get("errors") and not report.get("warnings"):
            lines.append("- No integrity issues found.")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    json_path = target / "integrity.json"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path
