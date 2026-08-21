import json

import pytest

from authorship_shift.semantic_plan import (
    apply_plan_draft,
    parse_plan_response,
    render_plan_extraction_prompt,
)


def _packet():
    return {
        "id": "ex-1",
        "genre": "science_summary",
        "split": "holdout",
        "instruction": "Explain the observation without claiming causation.",
        "content_atoms": [],
        "immutable_details": [],
        "required_qualifications": [],
        "target_text": (
            "The measurements differed across the two sites, but the observational design "
            "did not establish why the difference occurred."
        ),
        "provenance": {
            "kind": "public_domain",
            "source_id": "source-1",
            "license": "Public Domain (U.S. Government work)",
            "note": "reviewed",
        },
        "metadata": {"annotation_status": "pending", "target_sha256": "abc"},
    }


def test_plan_response_accepts_only_semantic_fields():
    draft = parse_plan_response(
        json.dumps(
            {
                "content_atoms": ["measurements differed by site", "cause was not established"],
                "immutable_details": [],
                "required_qualifications": ["observational evidence is not causal evidence"],
            }
        )
    )
    assert len(draft.content_atoms) == 2

    with pytest.raises(ValueError, match="packet-level"):
        parse_plan_response(
            json.dumps(
                {
                    "content_atoms": ["a", "b"],
                    "immutable_details": [],
                    "required_qualifications": [],
                    "target_text": "attempted override",
                }
            )
        )


def test_model_assisted_plan_never_becomes_ready_automatically():
    packet = _packet()
    draft = parse_plan_response(
        json.dumps(
            {
                "content_atoms": ["measurements differed by site", "cause was not established"],
                "immutable_details": [],
                "required_qualifications": ["do not infer causation"],
                "annotation_notes": "Check whether site identity matters.",
            }
        )
    )
    updated = apply_plan_draft(packet, draft)
    assert updated["metadata"]["annotation_status"] == "needs_review"
    assert updated["metadata"]["plan_extraction_method"] == "model_assisted"
    assert updated["target_text"] == packet["target_text"]
    assert updated["split"] == packet["split"]
    assert updated["provenance"] == packet["provenance"]


def test_plan_application_does_not_mutate_original_packet():
    packet = _packet()
    draft = parse_plan_response(
        json.dumps(
            {
                "content_atoms": ["one idea", "another idea"],
                "immutable_details": [],
                "required_qualifications": [],
            }
        )
    )
    updated = apply_plan_draft(packet, draft)
    assert packet["content_atoms"] == []
    assert packet["metadata"]["annotation_status"] == "pending"
    assert updated["content_atoms"] == ["one idea", "another idea"]


def test_rendered_prompt_requests_plan_only_and_contains_target():
    prompt = render_plan_extraction_prompt(_packet())
    assert "Human target text" in prompt
    assert _packet()["target_text"] in prompt
    assert "Do not include id, target_text, split, provenance" in prompt
    assert "Return JSON only" in prompt
