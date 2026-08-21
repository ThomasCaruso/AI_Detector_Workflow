from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any

EXTERNAL_PROVENANCE_KINDS = {"licensed", "public_domain"}
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
    revision = str(payload.get("revision_label", "")).strip() or None
    return SourceSnapshot(
        retrieved_at=retrieved_at,
        sha256=digest.lower(),
        artifact_kind=artifact_kind,
        revision_label=revision,
    )


def load_registry_snapshots(path: str | Path) -> tuple[dict[str, SourceSnapshot], list[str]]:
    """Validate exact-artifact snapshots without changing the registry parser.

    Approved externally sourced documents must pin the bytes actually reviewed
    for excerpting. Candidate/rejected records may remain incomplete, and
    user-owned/consented records may opt into the same snapshot contract.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
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
        provenance_kind = str(row.get("provenance_kind", "")).strip()
        snapshot_payload = row.get("source_snapshot")

        required = status == "approved" and provenance_kind in EXTERNAL_PROVENANCE_KINDS
        if snapshot_payload is None:
            if required:
                errors.append(
                    f"{source_id}: approved {provenance_kind} source requires source_snapshot "
                    "with retrieval time and exact artifact SHA-256"
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
