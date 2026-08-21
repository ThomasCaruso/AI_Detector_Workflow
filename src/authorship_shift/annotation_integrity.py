from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

FROZEN_MANIFEST_SCHEMA_VERSION = 1
FROZEN_MANIFEST_NAME = "_frozen_manifest.json"


def frozen_packet_payload(packet: dict[str, Any]) -> dict[str, Any]:
    """Return packet fields that annotation is never allowed to alter."""

    return {
        "id": packet.get("id"),
        "genre": packet.get("genre"),
        "split": packet.get("split"),
        "instruction": packet.get("instruction"),
        "target_text": packet.get("target_text"),
        "provenance": packet.get("provenance"),
    }


def frozen_packet_sha256(packet: dict[str, Any]) -> str:
    encoded = json.dumps(
        frozen_packet_payload(packet),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_frozen_manifest(packets: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(packets)
    fingerprints: dict[str, str] = {}
    for packet in rows:
        packet_id = str(packet.get("id", "")).strip()
        if not packet_id:
            raise ValueError("annotation packet id is required for frozen manifest")
        if packet_id in fingerprints:
            raise ValueError(f"duplicate annotation packet id {packet_id!r}")
        fingerprints[packet_id] = frozen_packet_sha256(packet)
    return {
        "schema_version": FROZEN_MANIFEST_SCHEMA_VERSION,
        "frozen_fields": [
            "id",
            "genre",
            "split",
            "instruction",
            "target_text",
            "provenance",
        ],
        "packets": fingerprints,
    }


def write_frozen_manifest(
    packets: Iterable[dict[str, Any]],
    annotations_dir: str | Path,
) -> Path:
    path = Path(annotations_dir) / FROZEN_MANIFEST_NAME
    if path.exists():
        raise FileExistsError(
            f"frozen annotation manifest already exists: {path}; do not silently replace the source-target contract"
        )
    payload = build_frozen_manifest(packets)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def verify_frozen_manifest(annotations_dir: str | Path) -> list[str]:
    root = Path(annotations_dir)
    manifest_path = root / FROZEN_MANIFEST_NAME
    if not manifest_path.exists():
        return [
            f"missing {FROZEN_MANIFEST_NAME}; annotation packets must be prepared through the frozen corpus pipeline"
        ]

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != FROZEN_MANIFEST_SCHEMA_VERSION:
        return [
            f"{FROZEN_MANIFEST_NAME}: unsupported schema_version {manifest.get('schema_version')!r}"
        ]
    expected = manifest.get("packets")
    if not isinstance(expected, dict):
        return [f"{FROZEN_MANIFEST_NAME}: packets must be an object"]

    errors: list[str] = []
    seen: set[str] = set()
    for packet_path in sorted(root.glob("*.json")):
        if packet_path.name == FROZEN_MANIFEST_NAME:
            continue
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        packet_id = str(packet.get("id", "")).strip()
        if not packet_id:
            errors.append(f"{packet_path.name}: packet id is missing")
            continue
        seen.add(packet_id)
        expected_hash = expected.get(packet_id)
        if expected_hash is None:
            errors.append(
                f"{packet_id}: packet is absent from frozen manifest; do not add annotations outside preparation"
            )
            continue
        actual_hash = frozen_packet_sha256(packet)
        if actual_hash != expected_hash:
            errors.append(
                f"{packet_id}: frozen source-target fields changed after preparation"
            )

    missing_files = sorted(set(expected) - seen)
    for packet_id in missing_files:
        errors.append(f"{packet_id}: annotation packet listed in frozen manifest is missing")
    return errors
