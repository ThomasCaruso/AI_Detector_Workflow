from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from typing import Any

ALLOWED_PLAN_KEYS = {
    "content_atoms",
    "immutable_details",
    "required_qualifications",
    "annotation_notes",
}


@dataclass(frozen=True)
class SemanticPlanDraft:
    content_atoms: tuple[str, ...]
    immutable_details: tuple[str, ...]
    required_qualifications: tuple[str, ...]
    annotation_notes: str | None = None


def _string_list(payload: dict[str, Any], field_name: str, *, minimum: int = 0) -> tuple[str, ...]:
    value = payload.get(field_name, [])
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    cleaned = tuple(str(item).strip() for item in value if str(item).strip())
    if len(cleaned) != len(value):
        raise ValueError(f"{field_name} contains an empty item")
    if len(cleaned) < minimum:
        raise ValueError(f"{field_name} requires at least {minimum} item(s)")
    return cleaned


def parse_plan_response(text: str) -> SemanticPlanDraft:
    """Parse a model/manual plan response without trusting packet-level fields."""

    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("semantic plan response must be a JSON object")
    unexpected = sorted(set(payload) - ALLOWED_PLAN_KEYS)
    if unexpected:
        raise ValueError(
            "semantic plan response contains packet-level or unknown fields that cannot be "
            f"accepted: {unexpected}"
        )

    notes = str(payload.get("annotation_notes", "")).strip() or None
    return SemanticPlanDraft(
        content_atoms=_string_list(payload, "content_atoms", minimum=2),
        immutable_details=_string_list(payload, "immutable_details"),
        required_qualifications=_string_list(payload, "required_qualifications"),
        annotation_notes=notes,
    )


def render_plan_extraction_prompt(packet: dict[str, Any]) -> str:
    """Render a plan-extraction task from one pending annotation packet.

    The extractor sees the target because its job is to annotate meaning, but it
    must return only compressed semantic fields. Later corpus validation checks
    every prompt-bearing field for long target-text spans before training.
    """

    excerpt_id = str(packet.get("id", "")).strip()
    target = str(packet.get("target_text", "")).strip()
    instruction = str(packet.get("instruction", "")).strip()
    if not excerpt_id or not target or not instruction:
        raise ValueError("packet requires id, instruction, and target_text")

    return f"""# AuthorshipShift semantic-plan annotation

You are annotating one authentic human-written target for a future semantic-plan -> prose training experiment.

## Original task/instruction
{instruction}

## Human target text
{target}

## Annotation rules
- Return JSON only.
- Summarize meaning; do not rewrite the target.
- Use 2-8 short content atoms for the normal case.
- Keep atoms lexically compressed. Do not copy long clauses or sentences from the target.
- `immutable_details` is only for exact identifiers whose surface identity matters: numbers, dates, names, technical identifiers, named programs, etc.
- `required_qualifications` is for uncertainty, causal limits, scope restrictions, caveats, or counterpoints that must survive realization.
- Do not add facts, names, numbers, or qualifications not supported by the target.
- Do not include id, target_text, split, provenance, metadata, or any other packet-level field.
- A later validator rejects long verbatim target spans even if this annotation is otherwise plausible.

Return exactly this shape:
{{
  "content_atoms": ["...", "..."],
  "immutable_details": [],
  "required_qualifications": [],
  "annotation_notes": "optional short note for the human reviewer"
}}
"""


def apply_plan_draft(packet: dict[str, Any], draft: SemanticPlanDraft) -> dict[str, Any]:
    """Apply suggested semantic fields while preserving all frozen packet fields.

    Model-assisted extraction never marks a packet ready for training. A human
    reviewer must inspect the plan and explicitly change `annotation_status` from
    `needs_review` to `ready`.
    """

    updated = deepcopy(packet)
    updated["content_atoms"] = list(draft.content_atoms)
    updated["immutable_details"] = list(draft.immutable_details)
    updated["required_qualifications"] = list(draft.required_qualifications)

    metadata = updated.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("packet metadata must be an object")
    metadata["annotation_status"] = "needs_review"
    metadata["plan_extraction_method"] = "model_assisted"
    if draft.annotation_notes:
        metadata["plan_annotation_notes"] = draft.annotation_notes
    return updated
