from __future__ import annotations

import json
from pathlib import Path

from .corpus_pipeline import REGISTRY_SCHEMA_VERSION, SourceRecord, parse_source_record


def load_source_registry_safe(path: str | Path) -> tuple[list[SourceRecord], list[str]]:
    """Load a registry for operator-facing commands without leaking tracebacks.

    The core parser intentionally raises on invalid records so library callers can
    fail fast. CLI surfaces use this wrapper to turn malformed JSON, BOM-encoded
    files, I/O failures, and record-validation errors into structured diagnostics.
    """

    try:
        text = Path(path).read_text(encoding="utf-8-sig")
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("source registry must be a JSON object")
        if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
            raise ValueError(
                f"source registry schema_version must be {REGISTRY_SCHEMA_VERSION}"
            )
        rows = payload.get("sources")
        if not isinstance(rows, list):
            raise ValueError("source registry requires a sources list")
        records = [
            parse_source_record(row, line_number=index)
            for index, row in enumerate(rows, start=1)
        ]
    except (OSError, UnicodeError, ValueError) as exc:
        return [], [str(exc)]
    return records, []
