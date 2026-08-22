from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable

TEXT_DERIVATION_SCHEMA_VERSION = 1
CORRECTIONS_SCHEMA_VERSION = 1
EXTRACTOR_NAME = "pypdf"
EXTRACTOR_VERSION = "6.15.0"
EXTRACTION_MODE = "plain"
NORMALIZATION_VERSION = "pdf-text-v1"

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}
_SPACE_CHARS = {
    "\u00a0",
    "\u1680",
    "\u2000",
    "\u2001",
    "\u2002",
    "\u2003",
    "\u2004",
    "\u2005",
    "\u2006",
    "\u2007",
    "\u2008",
    "\u2009",
    "\u200a",
    "\u202f",
    "\u205f",
    "\u3000",
}


@dataclass(frozen=True)
class PageText:
    page: int
    text: str


@dataclass(frozen=True)
class TextDerivation:
    artifact_sha256: str
    extractor_name: str
    extractor_version: str
    extraction_mode: str
    normalization_version: str
    base_text_sha256: str
    corrections_sha256: str | None
    canonical_text_sha256: str
    canonical_text_path: str

    def frozen_dict(self) -> dict[str, Any]:
        return {
            "artifact_sha256": self.artifact_sha256,
            "extractor_name": self.extractor_name,
            "extractor_version": self.extractor_version,
            "extraction_mode": self.extraction_mode,
            "normalization_version": self.normalization_version,
            "base_text_sha256": self.base_text_sha256,
            "corrections_sha256": self.corrections_sha256,
            "canonical_text_sha256": self.canonical_text_sha256,
        }


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_pdf_text(text: str) -> str:
    """Apply only deterministic, source-agnostic extraction cleanup.

    This deliberately does *not* de-hyphenate words or repair suspicious
    intra-word spaces. Those operations are ambiguous and must be recorded in a
    reviewed correction ledger instead of being guessed by regex.
    """

    value = text.replace("\r\n", "\n").replace("\r", "\n")
    for src, dest in _LIGATURES.items():
        value = value.replace(src, dest)
    for src in _SPACE_CHARS:
        value = value.replace(src, " ")
    value = value.replace("\t", " ")

    lines: list[str] = []
    for line in value.split("\n"):
        line = re.sub(r"[ ]{2,}", " ", line).rstrip()
        lines.append(line)
    return "\n".join(lines).strip()


def pages_sha256(pages: Iterable[PageText]) -> str:
    payload = [
        {"page": row.page, "text": row.text}
        for row in sorted(pages, key=lambda item: item.page)
    ]
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def corrections_sha256(payload: dict[str, Any]) -> str:
    semantic = {
        "schema_version": payload.get("schema_version"),
        "artifact_sha256": payload.get("artifact_sha256"),
        "base_text_sha256": payload.get("base_text_sha256"),
        "replacements": payload.get("replacements", []),
    }
    encoded = json.dumps(
        semantic,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def apply_reviewed_corrections(
    pages: Iterable[PageText],
    correction_payload: dict[str, Any] | None,
    *,
    artifact_sha256: str,
) -> tuple[list[PageText], str | None]:
    rows = [PageText(row.page, row.text) for row in pages]
    if correction_payload is None:
        return rows, None
    if correction_payload.get("schema_version") != CORRECTIONS_SCHEMA_VERSION:
        raise ValueError(
            f"corrections schema_version must be {CORRECTIONS_SCHEMA_VERSION}"
        )
    if correction_payload.get("artifact_sha256") != artifact_sha256:
        raise ValueError("corrections artifact_sha256 does not match reviewed PDF")

    base_hash = pages_sha256(rows)
    if correction_payload.get("base_text_sha256") != base_hash:
        raise ValueError("corrections base_text_sha256 does not match extracted base text")

    replacements = correction_payload.get("replacements")
    if not isinstance(replacements, list):
        raise ValueError("corrections replacements must be a list")

    page_map = {row.page: row.text for row in rows}
    for index, replacement in enumerate(replacements, start=1):
        if not isinstance(replacement, dict):
            raise ValueError(f"correction {index}: replacement must be an object")
        try:
            page_number = int(replacement["page"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"correction {index}: page must be an integer") from exc
        if page_number not in page_map:
            raise ValueError(f"correction {index}: page {page_number} is absent")
        old = str(replacement.get("old", ""))
        new = str(replacement.get("new", ""))
        if not old:
            raise ValueError(f"correction {index}: old text is required")
        if old == new:
            raise ValueError(f"correction {index}: no-op replacement is not allowed")
        expected_count = int(replacement.get("expected_count", 1))
        if expected_count < 1:
            raise ValueError(f"correction {index}: expected_count must be at least 1")
        actual_count = page_map[page_number].count(old)
        if actual_count != expected_count:
            raise ValueError(
                f"correction {index}: page {page_number} expected {expected_count} "
                f"occurrence(s) of {old!r}, found {actual_count}"
            )
        page_map[page_number] = page_map[page_number].replace(old, new, expected_count)

    corrected = [PageText(page, page_map[page]) for page in sorted(page_map)]
    return corrected, corrections_sha256(correction_payload)


def canonical_text_contains(canonical_pages: Iterable[PageText], target_text: str) -> bool:
    """Allow only whitespace reflow between canonical extraction and target_text."""

    canonical = " ".join(
        " ".join(row.text.split())
        for row in sorted(canonical_pages, key=lambda item: item.page)
    )
    target = " ".join(target_text.split())
    return bool(target) and target in canonical


def write_canonical_extraction(
    path: str | Path,
    *,
    source_id: str,
    artifact_sha256: str,
    base_pages: Iterable[PageText],
    canonical_pages: Iterable[PageText],
    correction_hash: str | None,
) -> dict[str, Any]:
    base_rows = list(base_pages)
    canonical_rows = list(canonical_pages)
    payload = {
        "schema_version": TEXT_DERIVATION_SCHEMA_VERSION,
        "source_id": source_id,
        "artifact_sha256": artifact_sha256,
        "extractor": {
            "name": EXTRACTOR_NAME,
            "version": EXTRACTOR_VERSION,
            "mode": EXTRACTION_MODE,
        },
        "normalization_version": NORMALIZATION_VERSION,
        "base_text_sha256": pages_sha256(base_rows),
        "corrections_sha256": correction_hash,
        "canonical_text_sha256": pages_sha256(canonical_rows),
        "pages": [
            {"page": row.page, "text": row.text}
            for row in canonical_rows
        ],
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def load_canonical_extraction(path: str | Path) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        return None, [f"canonical extraction could not be read: {exc}"]
    errors: list[str] = []
    if not isinstance(payload, dict):
        return None, ["canonical extraction must be a JSON object"]
    if payload.get("schema_version") != TEXT_DERIVATION_SCHEMA_VERSION:
        errors.append(
            f"canonical extraction schema_version must be {TEXT_DERIVATION_SCHEMA_VERSION}"
        )
    extractor = payload.get("extractor")
    if not isinstance(extractor, dict):
        errors.append("canonical extraction requires extractor metadata")
    else:
        expected = {
            "name": EXTRACTOR_NAME,
            "version": EXTRACTOR_VERSION,
            "mode": EXTRACTION_MODE,
        }
        for key, value in expected.items():
            if extractor.get(key) != value:
                errors.append(f"extractor.{key} must be {value!r}")
    if payload.get("normalization_version") != NORMALIZATION_VERSION:
        errors.append(f"normalization_version must be {NORMALIZATION_VERSION!r}")

    pages_payload = payload.get("pages")
    pages: list[PageText] = []
    if not isinstance(pages_payload, list):
        errors.append("canonical extraction requires pages list")
    else:
        try:
            pages = [
                PageText(page=int(row["page"]), text=str(row["text"]))
                for row in pages_payload
            ]
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"invalid canonical extraction page: {exc}")
    if pages and payload.get("canonical_text_sha256") != pages_sha256(pages):
        errors.append("canonical_text_sha256 does not match canonical pages")
    return (payload if not errors else None), errors


def parse_registry_text_derivation(
    row: dict[str, Any],
    *,
    registry_dir: Path,
) -> tuple[TextDerivation | None, list[str]]:
    source_id = str(row.get("source_id", "")).strip() or "source"
    status = str(row.get("status", "")).strip()
    snapshot = row.get("source_snapshot")
    artifact_kind = snapshot.get("artifact_kind") if isinstance(snapshot, dict) else None
    payload = row.get("source_text_derivation")

    required = status == "approved" and artifact_kind == "pdf"
    if payload is None:
        if required:
            return None, [
                f"{source_id}: approved PDF source requires source_text_derivation"
            ]
        return None, []
    if not isinstance(payload, dict):
        return None, [f"{source_id}: source_text_derivation must be an object"]

    errors: list[str] = []
    expected_strings = {
        "artifact_sha256": str(snapshot.get("sha256", "")) if isinstance(snapshot, dict) else "",
        "extractor_name": EXTRACTOR_NAME,
        "extractor_version": EXTRACTOR_VERSION,
        "extraction_mode": EXTRACTION_MODE,
        "normalization_version": NORMALIZATION_VERSION,
    }
    for key, expected in expected_strings.items():
        if payload.get(key) != expected:
            errors.append(f"{source_id}: source_text_derivation.{key} must be {expected!r}")

    for key in ("base_text_sha256", "canonical_text_sha256"):
        value = str(payload.get(key, ""))
        if not _SHA256_RE.fullmatch(value):
            errors.append(f"{source_id}: source_text_derivation.{key} must be SHA-256")
    correction_value = payload.get("corrections_sha256")
    if correction_value is not None and not _SHA256_RE.fullmatch(str(correction_value)):
        errors.append(f"{source_id}: source_text_derivation.corrections_sha256 must be SHA-256 or null")

    canonical_path_value = str(payload.get("canonical_text_path", "")).strip()
    if not canonical_path_value:
        errors.append(f"{source_id}: source_text_derivation.canonical_text_path is required")
        canonical_path = registry_dir
    else:
        canonical_path = (registry_dir / canonical_path_value).resolve()

    canonical_payload: dict[str, Any] | None = None
    if canonical_path_value:
        canonical_payload, canonical_errors = load_canonical_extraction(canonical_path)
        errors.extend(f"{source_id}: {item}" for item in canonical_errors)
    if canonical_payload is not None:
        if canonical_payload.get("source_id") != source_id:
            errors.append(f"{source_id}: canonical extraction source_id mismatch")
        for key in (
            "artifact_sha256",
            "base_text_sha256",
            "corrections_sha256",
            "canonical_text_sha256",
        ):
            if canonical_payload.get(key) != payload.get(key):
                errors.append(f"{source_id}: canonical extraction {key} mismatch")

    if errors:
        return None, errors
    return TextDerivation(
        artifact_sha256=str(payload["artifact_sha256"]),
        extractor_name=str(payload["extractor_name"]),
        extractor_version=str(payload["extractor_version"]),
        extraction_mode=str(payload["extraction_mode"]),
        normalization_version=str(payload["normalization_version"]),
        base_text_sha256=str(payload["base_text_sha256"]),
        corrections_sha256=(
            str(payload["corrections_sha256"])
            if payload.get("corrections_sha256") is not None
            else None
        ),
        canonical_text_sha256=str(payload["canonical_text_sha256"]),
        canonical_text_path=canonical_path_value,
    ), []


def load_registry_text_derivations(
    registry_path: str | Path,
) -> tuple[dict[str, TextDerivation], dict[str, list[PageText]], list[str]]:
    try:
        raw = json.loads(Path(registry_path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        return {}, {}, [f"source registry could not be read for text derivations: {exc}"]
    rows = raw.get("sources", []) if isinstance(raw, dict) else []
    if not isinstance(rows, list):
        return {}, {}, ["source registry requires a sources list"]

    derivations: dict[str, TextDerivation] = {}
    canonical_pages: dict[str, list[PageText]] = {}
    errors: list[str] = []
    registry_dir = Path(registry_path).resolve().parent
    for row in rows:
        if not isinstance(row, dict):
            continue
        source_id = str(row.get("source_id", "")).strip()
        derivation, row_errors = parse_registry_text_derivation(
            row,
            registry_dir=registry_dir,
        )
        errors.extend(row_errors)
        if derivation is None:
            continue
        canonical_path = (registry_dir / derivation.canonical_text_path).resolve()
        payload, canonical_errors = load_canonical_extraction(canonical_path)
        errors.extend(f"{source_id}: {item}" for item in canonical_errors)
        if payload is None:
            continue
        pages = [PageText(page=int(item["page"]), text=str(item["text"])) for item in payload["pages"]]
        derivations[source_id] = derivation
        canonical_pages[source_id] = pages
    return derivations, canonical_pages, errors
