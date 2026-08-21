from __future__ import annotations

from dataclasses import asdict, dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from .lora_data import LoraExample, load_jsonl, parse_example, validate_dataset

REGISTRY_SCHEMA_VERSION = 1
RAW_SCHEMA_VERSION = 1
ANNOTATION_SCHEMA_VERSION = 1

ALLOWED_SOURCE_STATUS = {"candidate", "approved", "rejected"}
ALLOWED_PROVENANCE_KINDS = {"user_owned", "licensed", "public_domain", "consented"}
DEFAULT_SPLIT_SEED = "authorship-shift-lora-v1"
DEFAULT_TRAIN_FRACTION = 0.80
DEFAULT_DEV_FRACTION = 0.10


@dataclass(frozen=True)
class SourceRecord:
    source_id: str
    title: str
    genre: str
    status: str
    provenance_kind: str
    rights_basis: str
    canonical_url: str | None = None
    author_or_agency: str | None = None
    license: str | None = None
    document_locator: str | None = None
    notes: str | None = None

    def provenance_dict(self) -> dict[str, Any]:
        return {
            "kind": self.provenance_kind,
            "source_id": self.source_id,
            "license": self.license,
            "note": self.rights_basis,
        }


@dataclass(frozen=True)
class RawExcerpt:
    id: str
    source_id: str
    genre: str
    instruction: str
    target_text: str
    excerpt_locator: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def target_sha256(self) -> str:
        normalized = " ".join(self.target_text.split()).encode("utf-8")
        return hashlib.sha256(normalized).hexdigest()


@dataclass
class RegistryValidationReport:
    source_count: int
    approved_count: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"valid": self.valid}


@dataclass
class AnnotationPreparationReport:
    excerpt_count: int
    packet_count: int
    split_counts: dict[str, int]
    errors: list[str] = field(default_factory=list)

    @property
    def valid(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self) | {"valid": self.valid}


def _required_string(payload: dict[str, Any], field_name: str, *, where: str) -> str:
    value = str(payload.get(field_name, "")).strip()
    if not value:
        raise ValueError(f"{where}: {field_name} is required")
    return value


def parse_source_record(payload: dict[str, Any], *, line_number: int | None = None) -> SourceRecord:
    where = f"source line {line_number}" if line_number is not None else "source"
    source_id = _required_string(payload, "source_id", where=where)
    title = _required_string(payload, "title", where=source_id)
    genre = _required_string(payload, "genre", where=source_id)
    status = _required_string(payload, "status", where=source_id)
    provenance_kind = _required_string(payload, "provenance_kind", where=source_id)
    rights_basis = str(payload.get("rights_basis", "")).strip()

    if status not in ALLOWED_SOURCE_STATUS:
        raise ValueError(f"{source_id}: status must be one of {sorted(ALLOWED_SOURCE_STATUS)}")
    if provenance_kind not in ALLOWED_PROVENANCE_KINDS:
        raise ValueError(
            f"{source_id}: provenance_kind must be one of {sorted(ALLOWED_PROVENANCE_KINDS)}"
        )
    if status == "approved" and not rights_basis:
        raise ValueError(f"{source_id}: approved sources require a rights_basis")

    license_name = str(payload.get("license", "")).strip() or None
    if status == "approved" and provenance_kind in {"licensed", "public_domain"} and not license_name:
        raise ValueError(
            f"{source_id}: approved {provenance_kind} sources require a license/public-domain label"
        )

    canonical_url = str(payload.get("canonical_url", "")).strip() or None
    if status == "approved" and provenance_kind in {"licensed", "public_domain"} and not canonical_url:
        raise ValueError(
            f"{source_id}: approved externally sourced material requires canonical_url"
        )

    return SourceRecord(
        source_id=source_id,
        title=title,
        genre=genre,
        status=status,
        provenance_kind=provenance_kind,
        rights_basis=rights_basis,
        canonical_url=canonical_url,
        author_or_agency=str(payload.get("author_or_agency", "")).strip() or None,
        license=license_name,
        document_locator=str(payload.get("document_locator", "")).strip() or None,
        notes=str(payload.get("notes", "")).strip() or None,
    )


def load_source_registry(path: str | Path) -> list[SourceRecord]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("source registry must be a JSON object")
    if payload.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ValueError(
            f"source registry schema_version must be {REGISTRY_SCHEMA_VERSION}"
        )
    rows = payload.get("sources")
    if not isinstance(rows, list):
        raise ValueError("source registry requires a sources list")
    return [parse_source_record(row, line_number=index) for index, row in enumerate(rows, start=1)]


def validate_source_registry(records: Iterable[SourceRecord]) -> RegistryValidationReport:
    rows = list(records)
    errors: list[str] = []
    warnings: list[str] = []
    seen: dict[str, int] = {}

    for row in rows:
        seen[row.source_id] = seen.get(row.source_id, 0) + 1
        if row.status == "candidate":
            warnings.append(
                f"{row.source_id}: candidate source cannot produce training examples until approved"
            )
        if row.status == "rejected":
            warnings.append(f"{row.source_id}: source is explicitly rejected")

    for source_id, count in sorted(seen.items()):
        if count > 1:
            errors.append(f"duplicate source_id {source_id!r} appears {count} times")

    return RegistryValidationReport(
        source_count=len(rows),
        approved_count=sum(1 for row in rows if row.status == "approved"),
        errors=errors,
        warnings=warnings,
    )


def parse_raw_excerpt(payload: dict[str, Any], *, line_number: int | None = None) -> RawExcerpt:
    where = f"raw line {line_number}" if line_number is not None else "raw excerpt"
    excerpt_id = _required_string(payload, "id", where=where)
    source_id = _required_string(payload, "source_id", where=excerpt_id)
    genre = _required_string(payload, "genre", where=excerpt_id)
    instruction = _required_string(payload, "instruction", where=excerpt_id)
    target_text = _required_string(payload, "target_text", where=excerpt_id)
    excerpt_locator = _required_string(payload, "excerpt_locator", where=excerpt_id)
    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError(f"{excerpt_id}: metadata must be an object")
    return RawExcerpt(
        id=excerpt_id,
        source_id=source_id,
        genre=genre,
        instruction=instruction,
        target_text=target_text,
        excerpt_locator=excerpt_locator,
        metadata=dict(metadata),
    )


def load_raw_excerpts(path: str | Path) -> list[RawExcerpt]:
    rows: list[RawExcerpt] = []
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError(f"line {line_number}: raw JSONL record must be an object")
        rows.append(parse_raw_excerpt(payload, line_number=line_number))
    return rows


def deterministic_split(
    source_id: str,
    *,
    seed: str = DEFAULT_SPLIT_SEED,
    train_fraction: float = DEFAULT_TRAIN_FRACTION,
    dev_fraction: float = DEFAULT_DEV_FRACTION,
) -> str:
    """Assign an entire source document to one split by stable hash.

    Split assignment depends only on ``seed`` and ``source_id``. Every excerpt
    from a document therefore stays together, and annotation/model outcomes can
    never influence whether that document becomes train, dev, or holdout data.
    """

    if not source_id.strip():
        raise ValueError("source_id is required")
    if not (0.0 < train_fraction < 1.0):
        raise ValueError("train_fraction must be between 0 and 1")
    if not (0.0 < dev_fraction < 1.0):
        raise ValueError("dev_fraction must be between 0 and 1")
    if train_fraction + dev_fraction >= 1.0:
        raise ValueError("train_fraction + dev_fraction must be below 1")

    digest = hashlib.sha256(f"{seed}\0{source_id}".encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") / float(2**64)
    if bucket < train_fraction:
        return "train"
    if bucket < train_fraction + dev_fraction:
        return "dev"
    return "holdout"


def prepare_annotation_packet(
    excerpt: RawExcerpt,
    source: SourceRecord,
    *,
    split_seed: str = DEFAULT_SPLIT_SEED,
) -> dict[str, Any]:
    if source.source_id != excerpt.source_id:
        raise ValueError(
            f"{excerpt.id}: source mismatch {excerpt.source_id!r} != {source.source_id!r}"
        )
    if source.status != "approved":
        raise ValueError(
            f"{excerpt.id}: source {source.source_id!r} is {source.status}, not approved"
        )
    if excerpt.genre != source.genre:
        raise ValueError(
            f"{excerpt.id}: excerpt genre {excerpt.genre!r} does not match source genre {source.genre!r}"
        )

    split = deterministic_split(source.source_id, seed=split_seed)
    metadata = dict(excerpt.metadata)
    metadata.update(
        {
            "annotation_schema_version": ANNOTATION_SCHEMA_VERSION,
            "source_title": source.title,
            "source_url": source.canonical_url,
            "excerpt_locator": excerpt.excerpt_locator,
            "target_sha256": excerpt.target_sha256,
            "split_seed": split_seed,
            "annotation_status": "pending",
        }
    )
    return {
        "id": excerpt.id,
        "genre": excerpt.genre,
        "split": split,
        "instruction": excerpt.instruction,
        "content_atoms": [],
        "immutable_details": [],
        "required_qualifications": [],
        "target_text": excerpt.target_text,
        "provenance": source.provenance_dict(),
        "metadata": metadata,
    }


def prepare_annotation_packets(
    excerpts: Iterable[RawExcerpt],
    sources: Iterable[SourceRecord],
    *,
    split_seed: str = DEFAULT_SPLIT_SEED,
) -> tuple[list[dict[str, Any]], AnnotationPreparationReport]:
    source_map = {row.source_id: row for row in sources}
    packets: list[dict[str, Any]] = []
    errors: list[str] = []
    split_counts = {"train": 0, "dev": 0, "holdout": 0}
    seen_ids: set[str] = set()

    rows = list(excerpts)
    for excerpt in rows:
        if excerpt.id in seen_ids:
            errors.append(f"duplicate raw excerpt id {excerpt.id!r}")
            continue
        seen_ids.add(excerpt.id)
        source = source_map.get(excerpt.source_id)
        if source is None:
            errors.append(
                f"{excerpt.id}: source_id {excerpt.source_id!r} is absent from source registry"
            )
            continue
        try:
            packet = prepare_annotation_packet(excerpt, source, split_seed=split_seed)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        packets.append(packet)
        split_counts[packet["split"]] += 1

    return packets, AnnotationPreparationReport(
        excerpt_count=len(rows),
        packet_count=len(packets),
        split_counts=split_counts,
        errors=errors,
    )


def write_annotation_packets(packets: Iterable[dict[str, Any]], out_dir: str | Path) -> list[Path]:
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for packet in packets:
        path = root / f"{packet['id']}.json"
        if path.exists():
            raise FileExistsError(
                f"annotation packet already exists: {path}; do not silently overwrite annotations"
            )
        path.write_text(json.dumps(packet, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


def load_completed_annotations(path: str | Path) -> list[LoraExample]:
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(root)
    examples: list[LoraExample] = []
    for file_path in sorted(root.glob("*.json")):
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict) or metadata.get("annotation_status") != "ready":
            continue
        examples.append(parse_example(payload))
    return examples


def write_training_jsonl(examples: Iterable[LoraExample], out_path: str | Path) -> None:
    rows = list(examples)
    report = validate_dataset(rows)
    if not report.valid:
        raise ValueError("dataset validation failed: " + "; ".join(report.errors))

    path = Path(out_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = {
                "id": row.id,
                "genre": row.genre,
                "split": row.split,
                "instruction": row.instruction,
                "content_atoms": list(row.content_atoms),
                "immutable_details": list(row.immutable_details),
                "required_qualifications": list(row.required_qualifications),
                "target_text": row.target_text,
                "provenance": {
                    "kind": row.provenance.kind,
                    "source_id": row.provenance.source_id,
                    "license": row.provenance.license,
                    "note": row.provenance.note,
                },
                "metadata": dict(row.metadata),
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
