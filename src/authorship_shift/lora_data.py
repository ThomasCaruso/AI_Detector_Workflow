from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
ALLOWED_SPLITS = {"train", "dev", "holdout"}
ALLOWED_PROVENANCE_KINDS = {"user_owned", "licensed", "public_domain", "consented"}
FORBIDDEN_OBJECTIVE_FIELDS = {
    "detector_score",
    "detector_target",
    "detector_label",
    "pangram_score",
    "quillbot_score",
}


@dataclass(frozen=True)
class Provenance:
    kind: str
    source_id: str
    license: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class LoraExample:
    id: str
    genre: str
    split: str
    instruction: str
    content_atoms: tuple[str, ...]
    immutable_details: tuple[str, ...]
    required_qualifications: tuple[str, ...]
    target_text: str
    provenance: Provenance
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def target_sha256(self) -> str:
        normalized = " ".join(self.target_text.split()).encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()

    @property
    def word_count(self) -> int:
        return len(self.target_text.split())


@dataclass
class DatasetValidationReport:
    example_count: int
    split_counts: dict[str, int]
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "example_count": self.example_count,
            "split_counts": dict(self.split_counts),
            "valid": self.valid,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _nonempty_strings(value: Any, *, field_name: str, example_id: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{example_id}: {field_name} must be a list")
    cleaned = tuple(str(item).strip() for item in value if str(item).strip())
    if len(cleaned) != len(value):
        raise ValueError(f"{example_id}: {field_name} contains an empty item")
    return cleaned


def parse_example(payload: dict[str, Any], *, line_number: int | None = None) -> LoraExample:
    where = f"line {line_number}" if line_number is not None else "example"
    example_id = str(payload.get("id", "")).strip()
    if not example_id:
        raise ValueError(f"{where}: id is required")

    forbidden = sorted(FORBIDDEN_OBJECTIVE_FIELDS.intersection(payload))
    if forbidden:
        raise ValueError(
            f"{example_id}: detector-oriented objective fields are not allowed: {forbidden}"
        )

    split = str(payload.get("split", "")).strip()
    if split not in ALLOWED_SPLITS:
        raise ValueError(f"{example_id}: split must be one of {sorted(ALLOWED_SPLITS)}")

    genre = str(payload.get("genre", "")).strip()
    instruction = str(payload.get("instruction", "")).strip()
    target_text = str(payload.get("target_text", "")).strip()
    if not genre:
        raise ValueError(f"{example_id}: genre is required")
    if not instruction:
        raise ValueError(f"{example_id}: instruction is required")
    if not target_text:
        raise ValueError(f"{example_id}: target_text is required")

    content_atoms = _nonempty_strings(
        payload.get("content_atoms", []), field_name="content_atoms", example_id=example_id
    )
    if len(content_atoms) < 2:
        raise ValueError(f"{example_id}: at least two content_atoms are required")

    immutable_details = _nonempty_strings(
        payload.get("immutable_details", []),
        field_name="immutable_details",
        example_id=example_id,
    )
    required_qualifications = _nonempty_strings(
        payload.get("required_qualifications", []),
        field_name="required_qualifications",
        example_id=example_id,
    )

    provenance_payload = payload.get("provenance")
    if not isinstance(provenance_payload, dict):
        raise ValueError(f"{example_id}: provenance object is required")
    kind = str(provenance_payload.get("kind", "")).strip()
    source_id = str(provenance_payload.get("source_id", "")).strip()
    license_name = provenance_payload.get("license")
    if kind not in ALLOWED_PROVENANCE_KINDS:
        raise ValueError(
            f"{example_id}: provenance.kind must be one of {sorted(ALLOWED_PROVENANCE_KINDS)}"
        )
    if not source_id:
        raise ValueError(f"{example_id}: provenance.source_id is required")
    if kind in {"licensed", "public_domain"} and not str(license_name or "").strip():
        raise ValueError(f"{example_id}: provenance.license is required for {kind}")

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"{example_id}: metadata must be an object")
    metadata_forbidden = sorted(FORBIDDEN_OBJECTIVE_FIELDS.intersection(metadata))
    if metadata_forbidden:
        raise ValueError(
            f"{example_id}: detector-oriented metadata fields are not allowed: {metadata_forbidden}"
        )

    return LoraExample(
        id=example_id,
        genre=genre,
        split=split,
        instruction=instruction,
        content_atoms=content_atoms,
        immutable_details=immutable_details,
        required_qualifications=required_qualifications,
        target_text=target_text,
        provenance=Provenance(
            kind=kind,
            source_id=source_id,
            license=str(license_name).strip() if license_name is not None else None,
            note=(
                str(provenance_payload.get("note")).strip()
                if provenance_payload.get("note") is not None
                else None
            ),
        ),
        metadata=dict(metadata),
    )


def load_jsonl(path: str | Path) -> list[LoraExample]:
    examples: list[LoraExample] = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"line {line_number}: each JSONL record must be an object")
        examples.append(parse_example(payload, line_number=line_number))
    return examples


def validate_dataset(examples: Iterable[LoraExample]) -> DatasetValidationReport:
    rows = list(examples)
    errors: list[str] = []
    warnings: list[str] = []
    split_counts = {split: 0 for split in sorted(ALLOWED_SPLITS)}

    ids: dict[str, int] = {}
    hashes: dict[str, list[LoraExample]] = {}
    source_splits: dict[str, set[str]] = {}

    for row in rows:
        split_counts[row.split] += 1
        ids[row.id] = ids.get(row.id, 0) + 1
        hashes.setdefault(row.target_sha256, []).append(row)
        source_splits.setdefault(row.provenance.source_id, set()).add(row.split)

        if row.word_count < 40:
            warnings.append(
                f"{row.id}: target_text has only {row.word_count} words; very short targets "
                "may teach formatting more than sustained prose behavior"
            )
        normalized_target = " ".join(row.target_text.split()).lower()
        # Every field below is rendered into the training prompt, so a verbatim
        # span in any of them leaks the completion into its own input. Checking
        # only content_atoms would leave three open paths.
        plan_fields: tuple[tuple[str, tuple[str, ...]], ...] = (
            ("content atom", row.content_atoms),
            ("immutable detail", row.immutable_details),
            ("required qualification", row.required_qualifications),
            ("instruction", (row.instruction,)),
        )
        for field_label, values in plan_fields:
            for value in values:
                if (
                    len(value.split()) >= 12
                    and " ".join(value.split()).lower() in normalized_target
                ):
                    errors.append(
                        f"{row.id}: {field_label} copies a 12+ word span from target_text; "
                        "semantic plans should not leak target prose"
                    )

    for example_id, count in sorted(ids.items()):
        if count > 1:
            errors.append(f"duplicate example id {example_id!r} appears {count} times")

    for digest, duplicates in hashes.items():
        if len(duplicates) > 1:
            labels = ", ".join(f"{row.id}:{row.split}" for row in duplicates)
            errors.append(f"duplicate target text ({digest[:12]}): {labels}")

    for source_id, splits in sorted(source_splits.items()):
        if len(splits) > 1:
            errors.append(
                f"source_id {source_id!r} crosses splits {sorted(splits)}; keep all excerpts "
                "from one source document in one split to prevent document leakage"
            )

    if rows and split_counts["holdout"] == 0:
        warnings.append("dataset contains no holdout examples")
    if rows and split_counts["dev"] == 0:
        warnings.append("dataset contains no dev examples")

    return DatasetValidationReport(
        example_count=len(rows),
        split_counts=split_counts,
        errors=errors,
        warnings=warnings,
    )
