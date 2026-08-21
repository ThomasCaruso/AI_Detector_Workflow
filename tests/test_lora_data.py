import json

import pytest

from authorship_shift.lora_data import load_jsonl, parse_example, validate_dataset


def _payload(**overrides):
    payload = {
        "id": "example-1",
        "genre": "technical_explanation",
        "split": "train",
        "instruction": "Explain the result clearly.",
        "content_atoms": ["latency increased", "retries amplified the slowdown"],
        "immutable_details": ["43 minutes"],
        "required_qualifications": ["trigger and amplifier are distinct"],
        "target_text": (
            "The outage began after the timeout setting changed, but the retry policy "
            "made the incident worse rather than triggering it independently. The "
            "distinction matters because correcting the timeout addresses the initiating "
            "event while retry behavior determines how severely the system degrades."
        ),
        "provenance": {
            "kind": "user_owned",
            "source_id": "owned-doc-1",
            "note": "Synthetic fixture owned by the project.",
        },
    }
    payload.update(overrides)
    return payload


def test_valid_example_parses():
    example = parse_example(_payload())
    assert example.id == "example-1"
    assert example.split == "train"
    assert example.target_sha256


def test_detector_objective_fields_are_rejected():
    payload = _payload(detector_score=0.12)
    with pytest.raises(ValueError, match="detector-oriented"):
        parse_example(payload)


def test_public_domain_and_licensed_examples_require_license():
    payload = _payload(
        provenance={"kind": "public_domain", "source_id": "book-1"}
    )
    with pytest.raises(ValueError, match="provenance.license"):
        parse_example(payload)


def test_document_source_may_not_cross_splits():
    train = parse_example(_payload(id="a", split="train"))
    holdout = parse_example(
        _payload(
            id="b",
            split="holdout",
            target_text=(
                "A separate excerpt from the same source document still belongs with "
                "the training split because document-level leakage can make a held-out "
                "evaluation look stronger than it is. The validator therefore groups "
                "all excerpts from one source identifier into one split."
            ),
        )
    )
    report = validate_dataset([train, holdout])
    assert report.valid is False
    assert any("crosses splits" in item for item in report.errors)


def test_duplicate_target_text_is_rejected_even_with_different_ids():
    first = parse_example(_payload(id="a"))
    second_payload = _payload(
        id="b",
        provenance={"kind": "user_owned", "source_id": "owned-doc-2"},
    )
    second = parse_example(second_payload)
    report = validate_dataset([first, second])
    assert report.valid is False
    assert any("duplicate target text" in item for item in report.errors)


def test_long_target_prose_may_not_be_copied_into_content_atoms():
    target = (
        "This deliberately long sentence contains enough consecutive words to show "
        "why the semantic plan cannot simply copy the target prose verbatim during training."
    )
    payload = _payload(
        target_text=target,
        content_atoms=[
            "This deliberately long sentence contains enough consecutive words to show why the semantic plan cannot simply copy",
            "the plan should remain compressed",
        ],
    )
    report = validate_dataset([parse_example(payload)])
    assert report.valid is False
    assert any("semantic plans should not leak" in item for item in report.errors)


@pytest.mark.parametrize(
    "field_name, label",
    [
        ("immutable_details", "immutable detail"),
        ("required_qualifications", "required qualification"),
    ],
)
def test_target_prose_may_not_leak_through_other_plan_list_fields(field_name, label):
    """Every plan field is rendered into the prompt, not just content_atoms.

    Guarding only content_atoms left three paths by which the completion could
    be recovered from its own input, which would train the model to copy.
    """

    target = (
        "This deliberately long sentence contains enough consecutive words to show "
        "why the semantic plan cannot simply copy the target prose verbatim during training."
    )
    payload = _payload(target_text=target, **{field_name: [target]})

    report = validate_dataset([parse_example(payload)])
    assert report.valid is False
    assert any(f"{label} copies a 12+ word span" in item for item in report.errors)


def test_target_prose_may_not_leak_through_the_instruction():
    target = (
        "This deliberately long sentence contains enough consecutive words to show "
        "why the semantic plan cannot simply copy the target prose verbatim during training."
    )
    payload = _payload(target_text=target, instruction=target)

    report = validate_dataset([parse_example(payload)])
    assert report.valid is False
    assert any("instruction copies a 12+ word span" in item for item in report.errors)


def test_short_plan_fields_that_echo_the_target_remain_allowed():
    """The guard targets verbatim leakage, not ordinary shared terminology."""

    payload = _payload(
        immutable_details=["43 minutes"],
        required_qualifications=["trigger and amplifier are distinct"],
    )
    report = validate_dataset([parse_example(payload)])
    assert report.valid is True


def test_jsonl_loader_and_split_counts(tmp_path):
    rows = [
        _payload(id="train-1", split="train"),
        _payload(
            id="dev-1",
            split="dev",
            provenance={"kind": "user_owned", "source_id": "owned-doc-2"},
            target_text=(
                "A development example uses a different source and different prose so "
                "the evaluator can tune training decisions without touching the final "
                "holdout. The exact content is unimportant here; the fixture exists to "
                "exercise the split accounting and JSONL loader."
            ),
        ),
        _payload(
            id="holdout-1",
            split="holdout",
            provenance={"kind": "user_owned", "source_id": "owned-doc-3"},
            target_text=(
                "A held-out example remains isolated from training and development. "
                "That separation is the core protection against claiming an adapter "
                "improved simply because it memorized prose or document-specific habits "
                "that were already present in the training corpus."
            ),
        ),
    ]
    path = tmp_path / "dataset.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")

    report = validate_dataset(load_jsonl(path))
    assert report.valid is True
    assert report.split_counts == {"dev": 1, "holdout": 1, "train": 1}
