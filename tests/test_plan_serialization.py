"""Tests for versioned semantic-plan serialization.

Every plan here is synthetic. No corpus document, no user prose.
"""

from __future__ import annotations

import pytest

from authorship_shift.plan_serialization import (
    SERIALIZER_V1,
    SERIALIZER_V2,
    SERIALIZER_VERSIONS,
    V2_FINAL_INSTRUCTION,
    field_positions,
    render,
    render_v1,
    render_v2,
)

PLAN = dict(
    instruction="Explain the specified material from the semantic plan.",
    content_atoms=["Alpha is stated first.", "Beta follows from alpha.", "Gamma closes the case."],
    immutable_details=["the figure is 42", "the place is Onetown"],
    required_qualifications=["the claim is hedged rather than asserted"],
)


# --- v1 must not drift -----------------------------------------------------

def test_v1_matches_the_trainer_renderer_byte_for_byte():
    """v1 is bound into frozen artifacts; it must equal the trainer's own output."""

    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "research" / "lora" / "train_personal_qlora.py"
    spec = importlib.util.spec_from_file_location("_trainer_for_serializer_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    class _Example:
        instruction = PLAN["instruction"]
        content_atoms = PLAN["content_atoms"]
        immutable_details = PLAN["immutable_details"]
        required_qualifications = PLAN["required_qualifications"]

    assert render_v1(**PLAN) == module.render_semantic_prompt(_Example())


def test_v1_renders_none_placeholder_for_empty_fields():
    out = render_v1(**{**PLAN, "immutable_details": [], "required_qualifications": []})

    assert "Immutable details:\n- none" in out
    assert "Required qualifications:\n- none" in out


def test_v1_orders_atoms_before_constraints():
    pos = field_positions(render_v1(**PLAN))

    assert pos["content_atoms"] < pos["immutable_details"] < pos["required_qualifications"]


# --- v2 ordering and marking ----------------------------------------------

def test_v2_puts_both_constraint_classes_before_content():
    pos = field_positions(render_v2(**PLAN))

    assert pos["required_qualifications"] < pos["content_atoms"]
    assert pos["immutable_details"] < pos["content_atoms"]


def test_v2_marks_constraints_as_non_negotiable():
    out = render_v2(**PLAN)

    assert "NON-NEGOTIABLE MEANING CONSTRAINTS" in out
    assert out.index("NON-NEGOTIABLE MEANING CONSTRAINTS") < out.index("CONTENT TO EXPRESS")


def test_v2_omits_empty_qualifications_without_placeholder():
    out = render_v2(**{**PLAN, "required_qualifications": []})

    assert "Required qualifications:" not in out
    assert "- none" not in out
    assert "Immutable details:" in out


def test_v2_omits_empty_immutable_details_without_placeholder():
    out = render_v2(**{**PLAN, "immutable_details": []})

    assert "Immutable details:" not in out
    assert "- none" not in out
    assert "Required qualifications:" in out


def test_v2_omits_the_whole_constraint_section_when_both_are_empty():
    out = render_v2(**{**PLAN, "immutable_details": [], "required_qualifications": []})

    assert "NON-NEGOTIABLE MEANING CONSTRAINTS" not in out
    assert "- none" not in out
    assert "CONTENT TO EXPRESS" in out


def test_v2_never_emits_a_none_placeholder_in_any_emptiness_combination():
    for imm in ([], PLAN["immutable_details"]):
        for qual in ([], PLAN["required_qualifications"]):
            out = render_v2(**{**PLAN, "immutable_details": imm, "required_qualifications": qual})
            assert "- none" not in out


# --- v2 content preservation ----------------------------------------------

def test_v2_represents_every_item_exactly_once():
    out = render_v2(**PLAN)

    for item in PLAN["content_atoms"] + PLAN["immutable_details"] + PLAN["required_qualifications"]:
        assert out.count(item) == 1


def test_v2_does_not_repeat_constraint_contents_in_the_final_instruction():
    out = render_v2(**PLAN)
    tail = out[out.index("Final instruction:"):]

    for item in PLAN["immutable_details"] + PLAN["required_qualifications"]:
        assert item not in tail


def test_v2_final_instruction_names_classes_and_requires_own_wording():
    out = render_v2(**PLAN)

    assert V2_FINAL_INSTRUCTION in out
    assert "own wording" in V2_FINAL_INSTRUCTION
    assert "Express all content atoms" in V2_FINAL_INSTRUCTION


def test_v2_does_not_instruct_verbatim_copying():
    out = render_v2(**PLAN).lower()

    for banned in ("verbatim", "copy the", "word for word", "exact wording"):
        assert banned not in out


def test_v2_includes_rhetorical_function_when_supplied():
    out = render_v2(**PLAN, communicative_function="explain")

    assert "RHETORICAL FUNCTION\nexplain" in out


def test_v2_omits_rhetorical_function_when_absent():
    assert "RHETORICAL FUNCTION" not in render_v2(**PLAN)


def test_v2_carries_the_same_data_as_v1():
    one, two = render_v1(**PLAN), render_v2(**PLAN)

    for item in PLAN["content_atoms"] + PLAN["immutable_details"] + PLAN["required_qualifications"]:
        assert item in one and item in two


# --- dispatch --------------------------------------------------------------

def test_render_dispatches_by_version():
    assert render(SERIALIZER_V1, **PLAN) == render_v1(**PLAN)
    assert render(SERIALIZER_V2, **PLAN) == render_v2(**PLAN)


def test_render_ignores_communicative_function_for_v1():
    assert render(SERIALIZER_V1, **PLAN, communicative_function="explain") == render_v1(**PLAN)


def test_unknown_version_raises_rather_than_defaulting():
    with pytest.raises(ValueError, match="unknown serializer version"):
        render("semantic-plan-v3", **PLAN)


def test_versions_are_pinned():
    assert SERIALIZER_VERSIONS == (SERIALIZER_V1, SERIALIZER_V2)
    assert SERIALIZER_V2 == "semantic-plan-v2-constraint-salient"


def test_field_positions_omits_absent_markers():
    pos = field_positions(render_v2(**{**PLAN, "required_qualifications": []}))

    assert "required_qualifications" not in pos
    assert "content_atoms" in pos
