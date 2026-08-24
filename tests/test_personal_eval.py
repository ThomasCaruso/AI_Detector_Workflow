"""Tests for the frozen holdout evaluation contract.

Fixtures are synthetic. Nothing here loads a model, generates text, or reads the
gitignored personal corpus.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import pytest

from authorship_shift.lora_data import parse_example
from authorship_shift.personal_eval import (
    CONDITION_ADAPTER,
    CONDITION_BASE,
    REQUIRED_CONDITIONS,
    BlindAssignment,
    ProtocolViolation,
    assert_blinded_records_are_clean,
    assert_no_target_leakage,
    assign_blind_labels,
    build_generation_plan,
    load_protocol,
    order_examples,
    per_example_seed,
    protocol_sha256,
    render_generation_prompt,
    split_blinded_outputs,
    verify_plan_contract,
)

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_PATH = ROOT / "research" / "lora" / "configs" / "personal_b_eval_protocol.json"

EVAL_PATH = ROOT / "research" / "lora" / "eval_personal_holdout.py"
EVAL_SPEC = importlib.util.spec_from_file_location("authorship_shift_eval_holdout", EVAL_PATH)
assert EVAL_SPEC and EVAL_SPEC.loader
EVAL = importlib.util.module_from_spec(EVAL_SPEC)
EVAL_SPEC.loader.exec_module(EVAL)

TRAIN_PATH = ROOT / "research" / "lora" / "train_personal_qlora.py"
TRAIN_SPEC = importlib.util.spec_from_file_location("authorship_shift_train_pq", TRAIN_PATH)
assert TRAIN_SPEC and TRAIN_SPEC.loader
TRAIN = importlib.util.module_from_spec(TRAIN_SPEC)
TRAIN_SPEC.loader.exec_module(TRAIN)

FROZEN_ADAPTER_SHA = "ec0179f460d99bf83118b15b564b15526f43a4f64931f1a206704d3f19ac1de8"
HEAVY_MODULES = {"torch", "transformers", "peft", "trl", "bitsandbytes", "datasets"}


def _example(example_id: str, source_id: str, seed_word: str = "held"):
    return parse_example(
        {
            "id": example_id,
            "genre": "personal_academic",
            "split": "holdout",
            "instruction": "Write the specified reflection from the semantic plan.",
            "content_atoms": ["A first claim.", "A second claim."],
            "immutable_details": ["the figure is Whitlock"],
            "required_qualifications": ["the claim is hedged"],
            "target_text": " ".join(f"{seed_word}{i}" for i in range(60)),
            "provenance": {
                "kind": "user_owned",
                "source_id": source_id,
                "license": None,
                "note": "Experiment B accepted academic writing",
            },
            "metadata": {"experiment_id": "personal-style-b-v1"},
        }
    )


def _twelve():
    return [_example(f"doc-{i:02d}#u00", f"doc-{i:02d}", f"w{i}") for i in range(12)]


@pytest.fixture
def protocol():
    return load_protocol(PROTOCOL_PATH)


# ---------------------------------------------------------------------------
# Protocol loading
# ---------------------------------------------------------------------------


def test_the_real_protocol_loads(protocol) -> None:
    assert protocol["protocol_id"] == "personal-style-b-holdout-eval-v1"
    assert protocol["base_model"] == "Qwen/Qwen3-8B"
    assert protocol["base_model_revision"] == "b968826d9c46dd6066d109eabc6255188de91218"
    assert tuple(protocol["conditions"]) == REQUIRED_CONDITIONS


def test_the_protocol_binds_the_frozen_adapter(protocol) -> None:
    assert protocol["adapter_artifact_sha256"] == FROZEN_ADAPTER_SHA


def test_the_protocol_pins_the_frozen_sampling_settings(protocol) -> None:
    generation = protocol["generation"]
    assert generation["do_sample"] is True
    assert generation["temperature"] == 0.7
    assert generation["top_p"] == 0.8
    assert generation["top_k"] == 20
    assert generation["min_p"] == 0.0
    assert generation["max_new_tokens"] == 768
    assert generation["num_return_sequences"] == 1
    assert protocol["prompt"]["enable_thinking"] is False
    assert protocol["holdout"]["expected_examples"] == 12
    assert protocol["generation_contract"]["expected_output_count"] == 24


def _write_protocol(tmp_path: Path, protocol, **overrides) -> Path:
    payload = copy.deepcopy(dict(protocol))
    for dotted, value in overrides.items():
        parts = dotted.split("__")
        node = payload
        for part in parts[:-1]:
            node = node[part]
        if value is None and parts[-1] in node:
            node[parts[-1]] = None
        else:
            node[parts[-1]] = value
    path = tmp_path / "protocol.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_an_unbound_adapter_is_rejected(tmp_path, protocol) -> None:
    path = _write_protocol(tmp_path, protocol, adapter_artifact_sha256=None)

    with pytest.raises(ProtocolViolation, match="adapter_artifact_sha256"):
        load_protocol(path)


def test_thinking_enabled_is_rejected(tmp_path, protocol) -> None:
    path = _write_protocol(tmp_path, protocol, prompt__enable_thinking=True)

    with pytest.raises(ProtocolViolation, match="enable_thinking"):
        load_protocol(path)


def test_condition_specific_prompting_is_rejected(tmp_path, protocol) -> None:
    path = _write_protocol(tmp_path, protocol, prompt__condition_specific_prompting=True)

    with pytest.raises(ProtocolViolation, match="condition_specific_prompting"):
        load_protocol(path)


def test_a_relaxed_generation_contract_is_rejected(tmp_path, protocol) -> None:
    path = _write_protocol(
        tmp_path, protocol, generation_contract__no_regeneration_after_scoring_begins=False
    )

    with pytest.raises(ProtocolViolation, match="no_regeneration_after_scoring_begins"):
        load_protocol(path)


def test_disabled_blinding_is_rejected(tmp_path, protocol) -> None:
    path = _write_protocol(tmp_path, protocol, blinding__enabled=False)

    with pytest.raises(ProtocolViolation, match="blinding"):
        load_protocol(path)


def test_protocol_digest_is_stable_and_content_sensitive(protocol) -> None:
    assert protocol_sha256(protocol) == protocol_sha256(dict(protocol))
    mutated = copy.deepcopy(protocol)
    mutated["generation"]["temperature"] = 0.9
    assert protocol_sha256(mutated) != protocol_sha256(protocol)


# ---------------------------------------------------------------------------
# Seeds and ordering
# ---------------------------------------------------------------------------


def test_the_seed_rule_matches_the_protocol_text() -> None:
    digest = hashlib.sha256(b"proto:example-1").hexdigest()
    expected = (int(digest, 16) & 0xFFFFFFFF) ^ 20260824

    assert per_example_seed("proto", "example-1", 20260824) == expected


def test_seeds_are_deterministic_and_distinct_per_example() -> None:
    a = per_example_seed("proto", "ex-a", 20260824)
    b = per_example_seed("proto", "ex-b", 20260824)

    assert a == per_example_seed("proto", "ex-a", 20260824)
    assert a != b


def test_seeds_fit_in_32_bits() -> None:
    for i in range(50):
        seed = per_example_seed("personal-style-b-holdout-eval-v1", f"doc-{i}", 20260824)
        assert 0 <= seed < 2**32


def test_examples_are_ordered_by_ascending_id() -> None:
    shuffled = [_example("doc-09#u00", "d9"), _example("doc-01#u00", "d1")]

    assert [e.id for e in order_examples(shuffled)] == ["doc-01#u00", "doc-09#u00"]


# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------


def test_the_eval_prompt_matches_the_training_template() -> None:
    # The protocol names train_personal_qlora::render_semantic_prompt as its
    # template_source, so the two must not drift apart.
    example = _example("doc-00#u00", "doc-00")

    assert render_generation_prompt(example) == TRAIN.render_semantic_prompt(example)


def test_the_prompt_never_contains_the_target(protocol) -> None:
    example = _example("doc-00#u00", "doc-00")

    prompt = render_generation_prompt(example)

    assert example.target_text not in prompt
    assert_no_target_leakage(example)


def test_an_atom_reproducing_target_wording_is_detected() -> None:
    target = " ".join(f"word{i}" for i in range(30))
    example = _example("doc-00#u00", "doc-00")
    leaky = parse_example(
        {
            "id": example.id,
            "genre": example.genre,
            "split": example.split,
            "instruction": example.instruction,
            "content_atoms": ["A first claim.", " ".join(target.split()[:12])],
            "immutable_details": [],
            "required_qualifications": ["hedged"],
            "target_text": target,
            "provenance": {"kind": "user_owned", "source_id": "doc-00"},
            "metadata": {},
        }
    )

    with pytest.raises(ProtocolViolation, match="content atom shares"):
        assert_no_target_leakage(leaky)


def test_immutable_details_may_overlap_the_target() -> None:
    # They must agree with the target exactly; that is the field's job. The real
    # holdout relies on this for meal compositions and lists of assumptions.
    target = "On the first day I had a rice bowl with beans, peppers, sauce and cheese."
    example = parse_example(
        {
            "id": "doc-00#u00",
            "genre": "personal_academic",
            "split": "holdout",
            "instruction": "Write the specified reflection from the semantic plan.",
            "content_atoms": ["The day was restaurant-based.", "Intake skewed to carbohydrate."],
            "immutable_details": [
                "the meal was a rice bowl with beans, peppers, sauce and cheese"
            ],
            "required_qualifications": ["not equated with being unhealthy"],
            "target_text": target,
            "provenance": {"kind": "user_owned", "source_id": "doc-00"},
            "metadata": {},
        }
    )

    assert_no_target_leakage(example)


def test_an_oversized_immutable_detail_is_rejected() -> None:
    example = parse_example(
        {
            "id": "doc-00#u00",
            "genre": "personal_academic",
            "split": "holdout",
            "instruction": "Write the specified reflection from the semantic plan.",
            "content_atoms": ["A.", "B."],
            "immutable_details": [" ".join(f"x{i}" for i in range(40))],
            "required_qualifications": ["hedged"],
            "target_text": " ".join(f"t{i}" for i in range(60)),
            "provenance": {"kind": "user_owned", "source_id": "doc-00"},
            "metadata": {},
        }
    )

    with pytest.raises(ProtocolViolation, match="word cap"):
        assert_no_target_leakage(example)


def test_an_immutable_detail_copied_wholesale_is_rejected() -> None:
    target = "The study examined how staff presence changes customer satisfaction across cultures and products."
    example = parse_example(
        {
            "id": "doc-00#u00",
            "genre": "personal_academic",
            "split": "holdout",
            "instruction": "Write the specified reflection from the semantic plan.",
            "content_atoms": ["A.", "B."],
            "immutable_details": [target],
            "required_qualifications": ["hedged"],
            "target_text": target,
            "provenance": {"kind": "user_owned", "source_id": "doc-00"},
            "metadata": {},
        }
    )

    with pytest.raises(ProtocolViolation, match="copied wholesale"):
        assert_no_target_leakage(example)


def test_the_prompt_carries_no_style_or_detector_language() -> None:
    prompt = render_generation_prompt(_example("doc-00#u00", "doc-00")).lower()

    for banned in ("like thomas", "author's voice", "detector", "human-sounding", "adapter"):
        assert banned not in prompt


# ---------------------------------------------------------------------------
# Generation plan
# ---------------------------------------------------------------------------


def test_the_plan_produces_exactly_24_tasks(protocol) -> None:
    plan = build_generation_plan(_twelve(), protocol)

    assert len(plan.units) == 12
    assert plan.expected_output_count == 24
    verify_plan_contract(plan, protocol)


def test_both_conditions_share_prompt_and_seed(protocol) -> None:
    plan = build_generation_plan(_twelve(), protocol)

    by_example: dict[str, list] = {}
    for task in plan.tasks:
        by_example.setdefault(task.example_id, []).append(task)

    assert len(by_example) == 12
    for tasks in by_example.values():
        assert tuple(t.condition for t in tasks) == (CONDITION_BASE, CONDITION_ADAPTER)
        assert len({t.prompt for t in tasks}) == 1
        assert len({t.seed for t in tasks}) == 1


def test_generation_kwargs_are_taken_from_the_protocol(protocol) -> None:
    plan = build_generation_plan(_twelve(), protocol)

    assert plan.generation_kwargs["temperature"] == 0.7
    assert plan.generation_kwargs["top_p"] == 0.8
    assert plan.generation_kwargs["top_k"] == 20
    assert plan.generation_kwargs["min_p"] == 0.0
    assert plan.generation_kwargs["max_new_tokens"] == 768


def test_a_wrong_example_count_is_rejected(protocol) -> None:
    with pytest.raises(ProtocolViolation, match="exactly 12"):
        build_generation_plan(_twelve()[:11], protocol)


def test_a_non_holdout_row_is_rejected(protocol) -> None:
    rows = _twelve()
    bad = parse_example(
        {
            **json.loads(json.dumps({
                "id": "doc-99#u00",
                "genre": "personal_academic",
                "split": "train",
                "instruction": "Write the specified reflection from the semantic plan.",
                "content_atoms": ["A.", "B."],
                "immutable_details": [],
                "required_qualifications": [],
                "target_text": "some words here that are long enough to pass validation",
                "provenance": {"kind": "user_owned", "source_id": "doc-99"},
                "metadata": {},
            }))
        }
    )
    rows[0] = bad

    with pytest.raises(ProtocolViolation, match="non-holdout"):
        build_generation_plan(rows, protocol)


def test_duplicate_example_ids_are_rejected(protocol) -> None:
    rows = _twelve()
    rows[1] = _example(rows[0].id, "other-doc", "zzz")

    with pytest.raises(ProtocolViolation, match="duplicate example ids"):
        build_generation_plan(rows, protocol)


def test_a_plan_with_the_wrong_output_count_fails_the_contract(protocol) -> None:
    plan = build_generation_plan(_twelve(), protocol)
    truncated = plan.__class__(
        protocol_id=plan.protocol_id,
        units=plan.units,
        tasks=plan.tasks[:-2],
        generation_kwargs=plan.generation_kwargs,
    )

    with pytest.raises(ProtocolViolation, match="22 outputs"):
        verify_plan_contract(truncated, protocol)


# ---------------------------------------------------------------------------
# Blinding
# ---------------------------------------------------------------------------


def test_blind_labels_are_deterministic_and_complete(protocol) -> None:
    plan = build_generation_plan(_twelve(), protocol)

    first = assign_blind_labels(plan, protocol)
    second = assign_blind_labels(plan, protocol)

    assert [a.label for a in first] == [a.label for a in second]
    assert len(first) == 24
    assert len({a.label for a in first}) == 24
    assert first[0].label == "EVAL-001"
    assert first[-1].label == "EVAL-024"


def test_blinding_actually_shuffles_conditions(protocol) -> None:
    plan = build_generation_plan(_twelve(), protocol)

    assignments = assign_blind_labels(plan, protocol)
    conditions = [a.condition for a in assignments]

    # Not simply all base then all adapter.
    assert conditions != [CONDITION_BASE] * 12 + [CONDITION_ADAPTER] * 12
    assert conditions.count(CONDITION_BASE) == 12
    assert conditions.count(CONDITION_ADAPTER) == 12


def test_blinded_outputs_and_mapping_are_written_separately(protocol) -> None:
    plan = build_generation_plan(_twelve(), protocol)
    assignments = assign_blind_labels(plan, protocol)
    texts = {
        (t.example_id, t.condition): f"generated text for {t.example_id}/{t.condition}"
        for t in plan.tasks
    }

    blinded, mapping = split_blinded_outputs(assignments, texts)

    assert len(blinded) == 24 and len(mapping) == 24
    assert all(set(record) == {"label", "output_text"} for record in blinded)
    assert all(set(row) == {"label", "example_id", "condition"} for row in mapping)


def test_a_label_naming_its_condition_is_rejected() -> None:
    assignments = (BlindAssignment("EVAL-001-adapter", "doc-00#u00", CONDITION_ADAPTER),)
    blinded = [{"label": "EVAL-001-adapter", "output_text": "some prose"}]

    with pytest.raises(ProtocolViolation, match="malformed label"):
        assert_blinded_records_are_clean(blinded, assignments)


def test_generated_prose_containing_a_condition_word_is_allowed(protocol) -> None:
    # "customer base" is ordinary English and appears in this corpus. Rejecting
    # output for its wording would bias the comparison.
    plan = build_generation_plan(_twelve(), protocol)
    assignments = assign_blind_labels(plan, protocol)
    blinded = [
        {"label": a.label, "output_text": "Growing a customer base takes adapter-like patience."}
        for a in assignments
    ]

    assert_blinded_records_are_clean(blinded, assignments)


def test_an_unassigned_label_is_rejected(protocol) -> None:
    plan = build_generation_plan(_twelve(), protocol)
    assignments = assign_blind_labels(plan, protocol)
    blinded = [{"label": "EVAL-999", "output_text": "prose"}]

    with pytest.raises(ProtocolViolation, match="unassigned label"):
        assert_blinded_records_are_clean(blinded, assignments)


def test_a_duplicate_label_is_rejected(protocol) -> None:
    plan = build_generation_plan(_twelve(), protocol)
    assignments = assign_blind_labels(plan, protocol)
    label = assignments[0].label
    blinded = [{"label": label, "output_text": "a"}, {"label": label, "output_text": "b"}]

    with pytest.raises(ProtocolViolation, match="duplicate blind label"):
        assert_blinded_records_are_clean(blinded, assignments)


def test_a_blinded_record_missing_its_text_is_rejected(protocol) -> None:
    plan = build_generation_plan(_twelve(), protocol)
    assignments = assign_blind_labels(plan, protocol)
    blinded = [{"label": assignments[0].label}]

    with pytest.raises(ProtocolViolation, match="missing fields"):
        assert_blinded_records_are_clean(blinded, assignments)


def test_extra_fields_on_a_blinded_record_are_rejected(protocol) -> None:
    assignments = (BlindAssignment("EVAL-001", "doc-00#u00", CONDITION_BASE),)
    blinded = [{"label": "EVAL-001", "output_text": "text", "source_id": "doc-00"}]

    with pytest.raises(ProtocolViolation, match="extra fields"):
        assert_blinded_records_are_clean(blinded, assignments)


def test_a_missing_generated_output_is_rejected(protocol) -> None:
    plan = build_generation_plan(_twelve(), protocol)
    assignments = assign_blind_labels(plan, protocol)
    texts = {(t.example_id, t.condition): "x" for t in plan.tasks[:-1]}

    with pytest.raises(ProtocolViolation, match="missing generated text"):
        split_blinded_outputs(assignments, texts)


# ---------------------------------------------------------------------------
# Adapter archive verification
# ---------------------------------------------------------------------------


def test_a_matching_archive_is_accepted(tmp_path, protocol) -> None:
    archive = tmp_path / "adapter.tar"
    archive.write_bytes(b"pretend adapter bytes")
    bound = dict(protocol)
    bound["adapter_artifact_sha256"] = hashlib.sha256(archive.read_bytes()).hexdigest()

    assert EVAL.verify_adapter_archive(archive, bound) == bound["adapter_artifact_sha256"]


def test_a_mismatched_archive_is_rejected(tmp_path, protocol) -> None:
    archive = tmp_path / "adapter.tar"
    archive.write_bytes(b"the wrong adapter")

    with pytest.raises(ProtocolViolation, match="does not match the protocol"):
        EVAL.verify_adapter_archive(archive, protocol)


def test_a_missing_archive_is_rejected(tmp_path, protocol) -> None:
    with pytest.raises(ProtocolViolation, match="not found"):
        EVAL.verify_adapter_archive(tmp_path / "absent.tar", protocol)


# ---------------------------------------------------------------------------
# Dry run
# ---------------------------------------------------------------------------


def _write_holdout(tmp_path: Path) -> Path:
    path = tmp_path / "holdout.jsonl"
    rows = []
    for i in range(12):
        rows.append(
            {
                "id": f"doc-{i:02d}#u00",
                "genre": "personal_academic",
                "split": "holdout",
                "instruction": "Write the specified reflection from the semantic plan.",
                "content_atoms": ["A first claim.", "A second claim."],
                "immutable_details": ["the figure is Whitlock"],
                "required_qualifications": ["the claim is hedged"],
                "target_text": " ".join(f"w{i}x{j}" for j in range(60)),
                "provenance": {
                    "kind": "user_owned",
                    "source_id": f"doc-{i:02d}",
                    "license": None,
                    "note": "Experiment B accepted academic writing",
                },
                "metadata": {"experiment_id": "personal-style-b-v1"},
            }
        )
    path.write_bytes(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")
    )
    return path


def test_dry_run_reports_the_full_contract(tmp_path, capsys) -> None:
    holdout = _write_holdout(tmp_path)

    rc = EVAL.main([str(holdout), "--protocol", str(PROTOCOL_PATH)])

    out = capsys.readouterr().out
    assert rc == 0
    assert "holdout_examples=12" in out
    assert "expected_outputs=24" in out
    assert "enable_thinking=false" in out
    assert "temperature=0.7" in out
    assert "top_p=0.8" in out
    assert "top_k=20" in out
    assert "min_p=0.0" in out
    assert "max_new_tokens=768" in out
    assert "identical_prompt_per_example=true" in out
    assert "identical_seed_per_example=true" in out
    assert "target_text_in_prompt=false" in out
    assert "unique_blind_labels=24" in out
    assert "model_loaded=false" in out
    assert "outputs_generated=0" in out
    assert "scoring_performed=false" in out
    assert f"adapter_artifact_sha256={FROZEN_ADAPTER_SHA}" in out


def test_dry_run_does_not_import_the_ml_stack(tmp_path) -> None:
    holdout = _write_holdout(tmp_path)
    already = HEAVY_MODULES & set(sys.modules)

    EVAL.main([str(holdout), "--protocol", str(PROTOCOL_PATH)])

    assert (HEAVY_MODULES & set(sys.modules)) == already


def test_dry_run_verifies_the_archive_when_given_one(tmp_path, capsys, protocol) -> None:
    holdout = _write_holdout(tmp_path)
    archive = tmp_path / "adapter.tar"
    archive.write_bytes(b"pretend adapter bytes")
    bound = _write_protocol(
        tmp_path,
        protocol,
        adapter_artifact_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
    )

    EVAL.main([str(holdout), "--protocol", str(bound), "--adapter-archive", str(archive)])

    assert "adapter_archive=verified" in capsys.readouterr().out


def test_dry_run_writes_no_files(tmp_path) -> None:
    holdout = _write_holdout(tmp_path)
    out_dir = tmp_path / "eval_out"

    EVAL.main(
        [str(holdout), "--protocol", str(PROTOCOL_PATH), "--output-dir", str(out_dir)]
    )

    assert not out_dir.exists()


def test_execute_refuses_without_an_adapter_archive(tmp_path) -> None:
    holdout = _write_holdout(tmp_path)

    with pytest.raises(ProtocolViolation, match="adapter-archive is required"):
        EVAL.main([str(holdout), "--protocol", str(PROTOCOL_PATH), "--execute"])


# ---------------------------------------------------------------------------
# Generation preflight
# ---------------------------------------------------------------------------


def test_preflight_reports_without_downloading(capsys) -> None:
    rc = EVAL.main(["--protocol", str(PROTOCOL_PATH), "--preflight"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "model_download=false" in out
    assert "generation_supported=" in out
    assert "os=" in out and "python=" in out


def test_preflight_needs_no_holdout_file(capsys) -> None:
    # The holdout must not be required merely to ask whether the machine works.
    rc = EVAL.main(["--protocol", str(PROTOCOL_PATH), "--preflight"])

    assert rc == 0
    assert "generation_supported=" in capsys.readouterr().out


def test_preflight_blocks_when_the_stack_is_absent(capsys) -> None:
    # No CUDA and no transformers on this machine, so it must refuse clearly
    # rather than implying the run could proceed.
    EVAL.main(["--protocol", str(PROTOCOL_PATH), "--preflight"])

    out = capsys.readouterr().out
    assert "generation_supported=false" in out
    assert "blocked_reason=" in out


def test_a_missing_holdout_argument_is_an_error_without_preflight() -> None:
    with pytest.raises(SystemExit):
        EVAL.main(["--protocol", str(PROTOCOL_PATH)])
