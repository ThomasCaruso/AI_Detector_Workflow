from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from typing import Any

ALLOWED_ARTIFACT_KINDS = {"pdf", "html", "text", "other"}
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


@dataclass(frozen=True)
class SourceSnapshot:
    retrieved_at: str
    sha256: str
    artifact_kind: str
    revision_label: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "retrieved_at": self.retrieved_at,
            "sha256": self.sha256.lower(),
            "artifact_kind": self.artifact_kind,
            "revision_label": self.revision_label,
        }


def _parse_retrieved_at(value: Any, *, source_id: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{source_id}: source_snapshot.retrieved_at is required")
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            f"{source_id}: source_snapshot.retrieved_at must be ISO-8601"
        ) from exc
    return text


def parse_source_snapshot(payload: Any, *, source_id: str) -> SourceSnapshot:
    if not isinstance(payload, dict):
        raise ValueError(f"{source_id}: source_snapshot must be an object")
    retrieved_at = _parse_retrieved_at(payload.get("retrieved_at"), source_id=source_id)
    digest = str(payload.get("sha256", "")).strip()
    if not _SHA256_RE.fullmatch(digest):
        raise ValueError(f"{source_id}: source_snapshot.sha256 must be a 64-digit SHA-256 hex digest")
    artifact_kind = str(payload.get("artifact_kind", "")).strip()
    if artifact_kind not in ALLOWED_ARTIFACT_KINDS:
        raise ValueError(
            f"{source_id}: source_snapshot.artifact_kind must be one of {sorted(ALLOWED_ARTIFACT_KINDS)}"
        )
    revision_value = payload.get("revision_label")
    revision = str(revision_value).strip() if revision_value is not None else None
    revision = revision or None
    return SourceSnapshot(
        retrieved_at=retrieved_at,
        sha256=digest.lower(),
        artifact_kind=artifact_kind,
        revision_label=revision,
    )


def _empty_snapshot_placeholder(payload: Any) -> bool:
    if payload is None:
        return True
    if not isinstance(payload, dict):
        return False
    return not any(
        str(payload.get(field) or "").strip()
        for field in ("retrieved_at", "sha256", "artifact_kind", "revision_label")
    )


def load_registry_snapshots(path: str | Path) -> tuple[dict[str, SourceSnapshot], list[str]]:
    """Validate exact-artifact snapshots for every approved source.

    Rights and artifact identity are separate concerns. Public-domain, licensed,
    user-owned, and consented documents can all change over time, so every
    approved source must pin the exact bytes reviewed for excerpting. Candidate
    and rejected records may keep the generated all-null snapshot placeholder.
    """

    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        return {}, [f"source registry could not be read: {exc}"]

    rows = payload.get("sources", []) if isinstance(payload, dict) else []
    if not isinstance(rows, list):
        return {}, ["source registry requires a sources list"]

    snapshots: dict[str, SourceSnapshot] = {}
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(f"source line {index}: source must be an object")
            continue
        source_id = str(row.get("source_id", "")).strip() or f"source line {index}"
        status = str(row.get("status", "")).strip()
        snapshot_payload = row.get("source_snapshot")

        if _empty_snapshot_placeholder(snapshot_payload):
            if status == "approved":
                errors.append(
                    f"{source_id}: approved source requires source_snapshot with retrieval "
                    "time and exact artifact SHA-256"
                )
            continue
        try:
            snapshots[source_id] = parse_source_snapshot(
                snapshot_payload,
                source_id=source_id,
            )
        except ValueError as exc:
            errors.append(str(exc))

    return snapshots, errors


def snapshot_set_sha256(snapshots: dict[str, SourceSnapshot]) -> str | None:
    """Fingerprint exact source artifacts independently of split assignment."""

    if not snapshots:
        return None
    payload = [
        {"source_id": source_id, **snapshots[source_id].to_dict()}
        for source_id in sorted(snapshots)
    ]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
