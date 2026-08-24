"""Approval, hashing, and dataset compilation for the personal-style experiment.

Turns reviewed semantic-plan packets into the three deterministic datasets the
personal QLoRA pilot consumes, and provides the digests that bind them:

    corpus_sha256            frozen source membership and split
    eligibility_mask_sha256  frozen post-freeze region judgements
    annotation_set_sha256    frozen approved packets
    <dataset>_sha256         frozen compiled bytes

Approval is a status transition and nothing else. Target text, semantic plans,
region ids, split, and provenance are carried through untouched; a compiler that
could edit them would make the digests meaningless.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Iterable, Mapping, Sequence

COMPILER_NAME = "personal-dataset-compiler"
COMPILER_VERSION = "v1"
DEFAULT_EXPERIMENT_ID = "personal-style-b-v1"
PERSONAL_GENRE = "personal_academic"
PERSONAL_PROVENANCE_KIND = "user_owned"
PERSONAL_PROVENANCE_NOTE = "Experiment B accepted academic writing"

NEEDS_REVIEW = "needs_review"
APPROVED = "approved"

# Fields the annotation-set digest binds. Anything omitted here could change
# without moving the hash, so this tuple is the contract.
ANNOTATION_HASH_FIELDS: tuple[str, ...] = (
    "example_id",
    "source_id",
    "split",
    "source_region_ids",
    "target_text",
    "semantic_plan",
    "review_status",
    "corpus_sha256",
    "eligibility_mask_sha256",
)

# Deterministic, style-neutral instruction per communicative function. These say
# what speech act to perform, never how to write it: no voice, register,
# sentence-length, vocabulary or detector language. The target distribution
# supplies the personalization signal, not the prompt.
INSTRUCTION_BY_FUNCTION: dict[str, str] = {
    "explain": "Explain the specified content from the semantic plan.",
    "argue": "Present the specified argument from the semantic plan.",
    "reflect": "Write the specified reflection from the semantic plan.",
    "summarize": "Summarize the specified material from the semantic plan.",
    "analyze": "Analyze the specified material from the semantic plan.",
    "respond": "Write the specified response from the semantic plan.",
    "persuade": "Present the specified persuasive case from the semantic plan.",
}
FALLBACK_INSTRUCTION = "Write the requested prose from the semantic plan."


def instruction_for(communicative_function: str | None) -> str:
    """Map a communicative function to its fixed instruction."""

    if not communicative_function:
        return FALLBACK_INSTRUCTION
    return INSTRUCTION_BY_FUNCTION.get(str(communicative_function).strip(), FALLBACK_INSTRUCTION)


def _canonical(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Approval
# ---------------------------------------------------------------------------


def approve_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Promote one reviewed packet to approved.

    A status transition only. Every other field is copied verbatim, so approval
    can never silently rewrite a target, a plan, a region list, or a split.
    """

    status = packet.get("review_status")
    if status == APPROVED:
        return dict(packet)
    if status != NEEDS_REVIEW:
        raise ValueError(
            f"{packet.get('example_id')!r}: cannot approve from review_status {status!r}"
        )
    approved = dict(packet)
    approved["review_status"] = APPROVED
    return approved


def approve_packets(packets: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [approve_packet(packet) for packet in packets]


def annotation_set_sha256(packets: Sequence[Mapping[str, Any]]) -> str:
    """Digest of an annotation set, in stable example_id order.

    Binds every field in :data:`ANNOTATION_HASH_FIELDS`. Ordering of the packets
    as supplied is irrelevant; ordering of a semantic plan's keys is irrelevant.
    Content is not.
    """

    missing = [
        f"{packet.get('example_id')!r}:{name}"
        for packet in packets
        for name in ANNOTATION_HASH_FIELDS
        if name not in packet
    ]
    if missing:
        raise ValueError(f"packets missing hash-bound fields: {sorted(missing)}")

    canonical = [
        {
            name: (
                list(packet[name])
                if name == "source_region_ids"
                else packet[name]
            )
            for name in ANNOTATION_HASH_FIELDS
        }
        for packet in sorted(packets, key=lambda item: str(item["example_id"]))
    ]
    return _sha256(_canonical(canonical))


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


def compile_row(
    packet: Mapping[str, Any],
    *,
    annotation_digest: str,
    experiment_id: str = DEFAULT_EXPERIMENT_ID,
) -> dict[str, Any]:
    """Compile one approved packet into the lora_data row schema."""

    if packet.get("review_status") != APPROVED:
        raise ValueError(
            f"{packet.get('example_id')!r}: only approved packets may be compiled"
        )
    plan = packet.get("semantic_plan") or {}
    return {
        "id": str(packet["example_id"]),
        "genre": PERSONAL_GENRE,
        "split": str(packet["split"]),
        "instruction": instruction_for(plan.get("communicative_function")),
        "content_atoms": list(plan.get("content_atoms") or []),
        "immutable_details": list(plan.get("immutable_details") or []),
        "required_qualifications": list(plan.get("required_qualifications") or []),
        "target_text": str(packet["target_text"]),
        "provenance": {
            "kind": PERSONAL_PROVENANCE_KIND,
            "source_id": str(packet["source_id"]),
            "license": None,
            "note": PERSONAL_PROVENANCE_NOTE,
        },
        "metadata": {
            "experiment_id": experiment_id,
            "source_region_ids": list(packet["source_region_ids"]),
            "corpus_sha256": str(packet["corpus_sha256"]),
            "eligibility_mask_sha256": str(packet["eligibility_mask_sha256"]),
            "annotation_set_sha256": annotation_digest,
        },
    }


def compile_rows(
    packets: Sequence[Mapping[str, Any]],
    *,
    annotation_digest: str,
    experiment_id: str = DEFAULT_EXPERIMENT_ID,
) -> list[dict[str, Any]]:
    """Compile approved packets in stable id order."""

    rows = [
        compile_row(packet, annotation_digest=annotation_digest, experiment_id=experiment_id)
        for packet in sorted(packets, key=lambda item: str(item["example_id"]))
    ]
    return rows


def serialize_rows(rows: Sequence[Mapping[str, Any]]) -> bytes:
    """Canonical JSONL bytes for a compiled dataset.

    Explicit "\\n" and UTF-8 bytes, so the digest is identical regardless of
    platform line-ending translation. The file written from this is byte-for-byte
    what :func:`dataset_sha256` hashes, which is what lets a trainer verify a
    dataset it did not compile.
    """

    return "".join(_canonical(row) + "\n" for row in rows).encode("utf-8")


def dataset_sha256(rows: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(serialize_rows(rows)).hexdigest()


def split_rows(rows: Sequence[Mapping[str, Any]], split: str) -> list[dict[str, Any]]:
    return [dict(row) for row in rows if row.get("split") == split]


def target_words(rows: Sequence[Mapping[str, Any]]) -> int:
    return sum(len(str(row.get("target_text", "")).split()) for row in rows)


def source_ids_by_split(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, set[str]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("split")), set()).add(
            str(row.get("provenance", {}).get("source_id"))
        )
    return {split: sorted(values) for split, values in sorted(grouped.items())}


@dataclass(frozen=True)
class DatasetManifest:
    experiment_id: str
    corpus_sha256: str
    eligibility_mask_sha256: str
    annotation_set_sha256: str
    full_dataset_sha256: str
    train_dataset_sha256: str
    holdout_dataset_sha256: str
    train_example_count: int
    holdout_example_count: int
    train_target_words: int
    holdout_target_words: int
    source_ids_by_split: dict[str, list[str]]
    compiler: str = f"{COMPILER_NAME}/{COMPILER_VERSION}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "corpus_sha256": self.corpus_sha256,
            "eligibility_mask_sha256": self.eligibility_mask_sha256,
            "annotation_set_sha256": self.annotation_set_sha256,
            "full_dataset_sha256": self.full_dataset_sha256,
            "train_dataset_sha256": self.train_dataset_sha256,
            "holdout_dataset_sha256": self.holdout_dataset_sha256,
            "train_example_count": self.train_example_count,
            "holdout_example_count": self.holdout_example_count,
            "train_target_words": self.train_target_words,
            "holdout_target_words": self.holdout_target_words,
            "source_ids_by_split": self.source_ids_by_split,
            "compiler": self.compiler,
        }


def build_manifest(
    rows: Sequence[Mapping[str, Any]],
    *,
    corpus_sha256: str,
    eligibility_mask_sha256: str,
    annotation_set_digest: str,
    experiment_id: str = DEFAULT_EXPERIMENT_ID,
) -> DatasetManifest:
    train = split_rows(rows, "train")
    holdout = split_rows(rows, "holdout")
    return DatasetManifest(
        experiment_id=experiment_id,
        corpus_sha256=corpus_sha256,
        eligibility_mask_sha256=eligibility_mask_sha256,
        annotation_set_sha256=annotation_set_digest,
        full_dataset_sha256=dataset_sha256(rows),
        train_dataset_sha256=dataset_sha256(train),
        holdout_dataset_sha256=dataset_sha256(holdout),
        train_example_count=len(train),
        holdout_example_count=len(holdout),
        train_target_words=target_words(train),
        holdout_target_words=target_words(holdout),
        source_ids_by_split=source_ids_by_split(rows),
    )
