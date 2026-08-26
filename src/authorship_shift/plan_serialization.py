"""Versioned rendering of a semantic plan into a training/generation prompt.

A semantic plan is data: content atoms, immutable details, required
qualifications, and a communicative function. How that data is laid out in a
prompt is a separate decision, and changing the layout changes what the model
attends to without changing what it is being asked to say.

Two versions live here.

``semantic-plan-v1`` reproduces the Experiment B/C layout byte-for-byte. It is
kept so those experiments stay reproducible; a test asserts equality against the
trainer's own renderer so the two cannot drift.

``semantic-plan-v2-constraint-salient`` reorders the same fields. Experiment C's
fidelity loss fell almost entirely on qualification preservation and immutable
detail accuracy, the two fields that v1 places last and smallest, while content
coverage - first and largest - held. v2 moves the constraint fields ahead of the
content, groups them under a heading that names them as non-negotiable, and
closes with a reminder that names the constraint classes without repeating their
contents.

What v2 deliberately does NOT do:

* it does not change any plan's data - identical fields, identical items;
* it does not ask for verbatim wording. A qualification is a semantic
  requirement about certainty, hedging, limitation, exception, condition or
  contrast, not a phrase to copy. The closing instruction says "use your own
  wording" precisely so that moving constraints earlier does not turn into a
  copying instruction;
* it does not make content atoms optional. Moving constraints first reorders
  emphasis; every atom is still required;
* it does not restate the constraint bullets at the end. Repeating their
  contents would inflate their share of the prompt and confound a presentation
  change with a duplication change.

Empty fields are omitted rather than rendered as a placeholder. v1's "- none"
occupies a labelled slot that says a constraint class exists and is empty; v2
simply does not raise the subject.
"""

from __future__ import annotations

from typing import Sequence

SERIALIZER_V1 = "semantic-plan-v1"
SERIALIZER_V2 = "semantic-plan-v2-constraint-salient"
SERIALIZER_VERSIONS = (SERIALIZER_V1, SERIALIZER_V2)

V2_FINAL_INSTRUCTION = (
    "Express all content atoms. Preserve every required qualification in meaning "
    "and every immutable detail accurately. Do not invent factual claims, names, "
    "numbers, relationships, or qualifications. Use your own wording and output "
    "only the requested prose."
)


def _bullets(items: Sequence[str]) -> str:
    return "\n".join(f"- {item}" for item in items)


def render_v1(
    *,
    instruction: str,
    content_atoms: Sequence[str],
    immutable_details: Sequence[str],
    required_qualifications: Sequence[str],
) -> str:
    """The Experiment B/C layout, reproduced byte-for-byte.

    Empty constraint fields render as ``- none``, which is what those runs did.
    Do not 'improve' this function: its output is bound into frozen artifacts.
    """

    atoms = _bullets(content_atoms)
    immutables = _bullets(immutable_details) if immutable_details else "- none"
    qualifications = _bullets(required_qualifications) if required_qualifications else "- none"
    return f"""Write the requested prose from the semantic plan below.

Task:
{instruction}

Content atoms:
{atoms}

Immutable details:
{immutables}

Required qualifications:
{qualifications}

Preserve meaning, certainty, and supplied details. Do not invent factual claims or names."""


def render_v2(
    *,
    instruction: str,
    content_atoms: Sequence[str],
    immutable_details: Sequence[str],
    required_qualifications: Sequence[str],
    communicative_function: str | None = None,
) -> str:
    """Constraint-salient layout: same data, constraints first and marked mandatory."""

    sections: list[str] = [
        "Write the requested prose from the semantic plan below.",
        f"Task:\n{instruction}",
    ]

    constraint_blocks: list[str] = []
    if required_qualifications:
        constraint_blocks.append(f"Required qualifications:\n{_bullets(required_qualifications)}")
    if immutable_details:
        constraint_blocks.append(f"Immutable details:\n{_bullets(immutable_details)}")
    if constraint_blocks:
        # The heading exists only to mark a section that has content. With both
        # constraint classes empty there is nothing to mark, so it is omitted
        # rather than left standing over an absence.
        sections.append("NON-NEGOTIABLE MEANING CONSTRAINTS")
        sections.extend(constraint_blocks)

    sections.append(f"CONTENT TO EXPRESS\n{_bullets(content_atoms)}")
    if communicative_function:
        sections.append(f"RHETORICAL FUNCTION\n{communicative_function}")
    sections.append(f"Final instruction:\n{V2_FINAL_INSTRUCTION}")
    return "\n\n".join(sections)


def render(version: str, **fields) -> str:
    """Dispatch by explicit version. Unknown versions raise rather than default."""

    if version == SERIALIZER_V1:
        fields.pop("communicative_function", None)
        return render_v1(**fields)
    if version == SERIALIZER_V2:
        return render_v2(**fields)
    raise ValueError(f"unknown serializer version {version!r}; known: {SERIALIZER_VERSIONS}")


def field_positions(text: str) -> dict[str, float]:
    """Fractional start position of each field, for comparing layouts.

    Returns only markers present in the text, so a layout that omits an empty
    field reports no position for it instead of a misleading zero.
    """

    markers = {
        "content_atoms": ("Content atoms:", "CONTENT TO EXPRESS"),
        "immutable_details": ("Immutable details:",),
        "required_qualifications": ("Required qualifications:",),
        "final_reminder": ("Preserve meaning, certainty", "Final instruction:"),
        "constraint_heading": ("NON-NEGOTIABLE MEANING CONSTRAINTS",),
        "rhetorical_function": ("RHETORICAL FUNCTION",),
    }
    length = len(text)
    out: dict[str, float] = {}
    for name, candidates in markers.items():
        for marker in candidates:
            index = text.find(marker)
            if index >= 0:
                out[name] = index / length
                break
    return out
