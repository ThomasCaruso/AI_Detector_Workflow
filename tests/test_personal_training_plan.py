"""Tests for the personal QLoRA entry point.

Fixtures are synthetic. Nothing here downloads a model, imports the ML stack, or
reads the gitignored personal corpus.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest

from authorship_shift.lora_data import load_jsonl
from authorship_shift.personal_dataset import (
    annotation_set_sha256,
    approve_packets,
    build_manifest,
    compile_rows,
    serialize_rows,
    split_rows,
)

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "research" / "lora" / "train_personal_qlora.py"
SPEC = importlib.util.spec_from_file_location("authorship_shift_train_personal_qlora", MODULE_PATH)
assert SPEC and SPEC.loader
TRAIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRAIN)

GENERAL_PATH = ROOT / "research" / "lora" / "train_qlora.py"
GENERAL_SPEC = importlib.util.spec_from_file_location(
    "authorship_shift_train_qlora_general", GENERAL_PATH
)
assert GENERAL_SPEC and GENERAL_SPEC.loader
GENERAL = importlib.util.module_from_spec(GENERAL_SPEC)
GENERAL_SPEC.loader.exec_module(GENERAL)

CONFIG_PATH = ROOT / "research" / "lora" / "configs" / "qwen3_8b_personal_b_qlora.json"
CORPUS = "c" * 64
MASK = "m" * 64
HEAVY_MODULES = {"torch", "transformers", "peft", "trl", "bitsandbytes", "datasets", "accelerate"}


def _packet(example_id, split, source_id, seed):
    return {
        "example_id": example_id,
        "source_id": source_id,
        "split": split,
        "source_region_ids": [f"{source_id}:b0000"],
        "corpus_sha256": CORPUS,
        "eligibility_mask_sha256": MASK,
        "target_text": " ".join(f"{seed}{i}" for i in range(60)),
        "semantic_plan": {
            "content_atoms": ["A first claim.", "A second claim."],
            "immutable_details": ["the figure is Whitlock"],
            "required_qualifications": ["the claim is hedged"],
            "communicative_function": "reflect",
        },
        "review_status": "needs_review",
    }


@pytest.fixture
def compiled(tmp_path: Path):
    """A frozen personal dataset on disk, with its manifest."""

    packets = approve_packets(
        [
            _packet("essay#u00", "train", "essay", "alpha"),
            _packet("essay#u01", "train", "essay", "beta"),
            _packet("diary#u00", "holdout", "diary", "gamma"),
        ]
    )
    digest = annotation_set_sha256(packets)
    rows = compile_rows(packets, annotation_digest=digest)
    train = split_rows(rows, "train")
    holdout = split_rows(rows, "holdout")

    train_path = tmp_path / "train.jsonl"
    holdout_path = tmp_path / "holdout.jsonl"
    train_path.write_bytes(serialize_rows(train))
    holdout_path.write_bytes(serialize_rows(holdout))

    manifest = build_manifest(
        rows,
        corpus_sha256=CORPUS,
        eligibility_mask_sha256=MASK,
        annotation_set_digest=digest,
    ).to_dict()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    return {
        "rows": rows,
        "train_path": train_path,
        "holdout_path": holdout_path,
        "manifest_path": manifest_path,
        "manifest": manifest,
    }


def _rewrite(path: Path, rows) -> None:
    path.write_bytes(serialize_rows(rows))


def _verify(compiled, manifest_overrides=None, dataset_path=None):
    manifest = dict(compiled["manifest"])
    manifest.update(manifest_overrides or {})
    path = dataset_path or compiled["train_path"]
    TRAIN.verify_train_dataset(path, manifest, load_jsonl(path))


# ---------------------------------------------------------------------------
# Accepting the frozen dataset
# ---------------------------------------------------------------------------


def test_the_frozen_train_dataset_is_accepted(compiled) -> None:
    _verify(compiled)


def test_dry_run_reports_the_bound_digests(compiled, capsys) -> None:
    config = TRAIN.load_config(CONFIG_PATH)
    examples = load_jsonl(compiled["train_path"])

    rc = TRAIN.dry_run(config, compiled["manifest"], examples, compiled["train_path"])

    out = capsys.readouterr().out
    assert rc == 0
    assert "dataset_valid=true" in out
    assert "experiment=personal-style-b-v1" in out
    assert "train_examples=2" in out
    assert "holdout_loaded=false" in out
    assert f"corpus_sha256={CORPUS}" in out
    assert f"eligibility_mask_sha256={MASK}" in out
    assert "mode=dry-run" in out
    assert "model_download=false" in out
    assert "eval_strategy=no" in out


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_a_holdout_row_in_the_train_dataset_is_refused(compiled) -> None:
    poisoned = [*split_rows(compiled["rows"], "train"), *split_rows(compiled["rows"], "holdout")]
    _rewrite(compiled["train_path"], poisoned)

    with pytest.raises(TRAIN.DatasetContractError, match="non-train rows"):
        _verify(
            compiled,
            manifest_overrides={
                "train_dataset_sha256": __import__("hashlib")
                .sha256(compiled["train_path"].read_bytes())
                .hexdigest()
            },
        )


def test_a_dataset_hash_mismatch_is_refused(compiled) -> None:
    with pytest.raises(TRAIN.DatasetContractError, match="does not match manifest"):
        _verify(compiled, manifest_overrides={"train_dataset_sha256": "f" * 64})


def test_an_experiment_id_mismatch_is_refused(compiled) -> None:
    with pytest.raises(TRAIN.DatasetContractError, match="experiment_id"):
        _verify(compiled, manifest_overrides={"experiment_id": "some-other-run"})


@pytest.mark.parametrize(
    "digest_field",
    ["corpus_sha256", "eligibility_mask_sha256", "annotation_set_sha256"],
)
def test_a_bound_digest_mismatch_is_refused(compiled, digest_field: str) -> None:
    with pytest.raises(TRAIN.DatasetContractError, match=digest_field):
        _verify(compiled, manifest_overrides={digest_field: "f" * 64})


def test_a_row_whose_digest_disagrees_with_the_manifest_is_refused(compiled) -> None:
    rows = split_rows(compiled["rows"], "train")
    rows[0] = {
        **rows[0],
        "metadata": {**rows[0]["metadata"], "corpus_sha256": "f" * 64},
    }
    _rewrite(compiled["train_path"], rows)
    import hashlib

    with pytest.raises(TRAIN.DatasetContractError, match="corpus_sha256"):
        _verify(
            compiled,
            manifest_overrides={
                "train_dataset_sha256": hashlib.sha256(
                    compiled["train_path"].read_bytes()
                ).hexdigest()
            },
        )


def test_duplicate_ids_are_refused(compiled) -> None:
    rows = split_rows(compiled["rows"], "train")
    rows[1] = {**rows[1], "id": rows[0]["id"]}
    _rewrite(compiled["train_path"], rows)
    import hashlib

    with pytest.raises(TRAIN.DatasetContractError, match="duplicate example id"):
        _verify(
            compiled,
            manifest_overrides={
                "train_dataset_sha256": hashlib.sha256(
                    compiled["train_path"].read_bytes()
                ).hexdigest()
            },
        )


def test_duplicate_target_text_is_refused(compiled) -> None:
    rows = split_rows(compiled["rows"], "train")
    rows[1] = {**rows[1], "target_text": rows[0]["target_text"]}
    _rewrite(compiled["train_path"], rows)
    import hashlib

    with pytest.raises(TRAIN.DatasetContractError, match="duplicate target text"):
        _verify(
            compiled,
            manifest_overrides={
                "train_dataset_sha256": hashlib.sha256(
                    compiled["train_path"].read_bytes()
                ).hexdigest()
            },
        )


def test_non_user_owned_provenance_is_refused(compiled) -> None:
    rows = split_rows(compiled["rows"], "train")
    rows[0] = {
        **rows[0],
        "provenance": {**rows[0]["provenance"], "kind": "public_domain", "license": "CC0"},
    }
    _rewrite(compiled["train_path"], rows)
    import hashlib

    with pytest.raises(TRAIN.DatasetContractError, match="provenance.kind"):
        _verify(
            compiled,
            manifest_overrides={
                "train_dataset_sha256": hashlib.sha256(
                    compiled["train_path"].read_bytes()
                ).hexdigest()
            },
        )


def test_a_detector_field_is_refused_at_parse_time(compiled) -> None:
    rows = split_rows(compiled["rows"], "train")
    rows[0] = {**rows[0], "detector_score": 0.1}
    _rewrite(compiled["train_path"], rows)

    with pytest.raises(ValueError, match="detector-oriented"):
        load_jsonl(compiled["train_path"])


def test_an_empty_train_dataset_is_refused(compiled) -> None:
    _rewrite(compiled["train_path"], [])
    import hashlib

    with pytest.raises(TRAIN.DatasetContractError, match="empty"):
        _verify(
            compiled,
            manifest_overrides={
                "train_dataset_sha256": hashlib.sha256(
                    compiled["train_path"].read_bytes()
                ).hexdigest()
            },
        )


def test_a_row_count_disagreement_is_refused(compiled) -> None:
    with pytest.raises(TRAIN.DatasetContractError, match="train_example_count"):
        _verify(compiled, manifest_overrides={"train_example_count": 99})


# ---------------------------------------------------------------------------
# The two "never" guarantees
# ---------------------------------------------------------------------------


def test_the_dry_run_never_opens_the_holdout_file(compiled) -> None:
    holdout = compiled["holdout_path"].resolve()
    opened: list[str] = []

    def hook(event, args):
        if event == "open":
            try:
                opened.append(str(Path(args[0]).resolve()))
            except Exception:
                opened.append(str(args[0]))

    sys.addaudithook(hook)
    TRAIN.main(
        [
            str(compiled["train_path"]),
            "--manifest",
            str(compiled["manifest_path"]),
            "--config",
            str(CONFIG_PATH),
        ]
    )

    assert str(holdout) not in opened
    assert not any("holdout" in path for path in opened)


def test_the_trainer_runs_without_the_holdout_file_present(compiled) -> None:
    compiled["holdout_path"].unlink()

    rc = TRAIN.main(
        [
            str(compiled["train_path"]),
            "--manifest",
            str(compiled["manifest_path"]),
            "--config",
            str(CONFIG_PATH),
        ]
    )

    assert rc == 0


def test_the_dry_run_does_not_import_the_ml_stack(compiled) -> None:
    already = HEAVY_MODULES & set(sys.modules)

    TRAIN.main(
        [
            str(compiled["train_path"]),
            "--manifest",
            str(compiled["manifest_path"]),
            "--config",
            str(CONFIG_PATH),
        ]
    )

    assert (HEAVY_MODULES & set(sys.modules)) == already


def test_execute_checks_the_contract_before_any_heavy_import(compiled) -> None:
    # A rejected dataset must not reach a model download. If verification ran
    # after the imports, this would raise ImportError instead.
    config = TRAIN.load_config(CONFIG_PATH)
    manifest = {**compiled["manifest"], "train_dataset_sha256": "f" * 64}

    with pytest.raises(TRAIN.DatasetContractError):
        TRAIN.execute(
            config, manifest, load_jsonl(compiled["train_path"]), compiled["train_path"]
        )


def test_preflight_reports_without_downloading(capsys) -> None:
    rc = TRAIN.preflight()

    out = capsys.readouterr().out
    assert rc == 0
    assert "model_download=false" in out
    assert "qlora_4bit_supported=" in out
    assert "os=" in out and "python=" in out


# ---------------------------------------------------------------------------
# Config and separation from the general trainer
# ---------------------------------------------------------------------------


def test_the_personal_config_matches_the_precommitted_hyperparameters() -> None:
    config = TRAIN.load_config(CONFIG_PATH)

    assert config["base_model"] == "Qwen/Qwen3-8B"
    assert config["output_dir"] == "artifacts/lora/qwen3-8b-personal-b-v1"
    assert config["training"]["num_train_epochs"] == 2.0
    assert config["training"]["learning_rate"] == 0.0002
    assert config["training"]["max_length"] == 2048
    assert config["training"]["gradient_accumulation_steps"] == 16
    assert config["training"]["seed"] == 20260821
    assert config["quantization"] == {
        "load_in_4bit": True,
        "bnb_4bit_quant_type": "nf4",
        "bnb_4bit_use_double_quant": True,
    }
    assert config["lora"]["r"] == 16
    assert config["lora"]["lora_alpha"] == 32
    assert config["lora"]["lora_dropout"] == 0.05
    assert config["lora"]["target_modules"] == "all-linear"
    assert config["objective"]["completion_only_loss"] is True
    assert config["objective"]["commercial_detector_objective"] is False


def test_the_personal_config_does_not_overwrite_the_general_one() -> None:
    general = json.loads(
        (ROOT / "research" / "lora" / "configs" / "qwen3_8b_qlora.json").read_text(
            encoding="utf-8"
        )
    )

    assert general["output_dir"] == "artifacts/lora/qwen3-8b-pilot"
    assert general["name"] == "qwen3-8b-qlora-pilot"
    assert "experiment_id" not in general


def test_the_general_trainer_still_requires_dev_and_holdout_and_genre_coverage() -> None:
    # The personal contract must not have loosened the decision-grade one.
    source = GENERAL_PATH.read_text(encoding="utf-8")

    assert "dataset contains no development examples" in source
    assert "dataset contains no holdout examples" in source
    assert "decision-grade genre x split coverage" in source
    # And no generic bypass flag was introduced.
    for bypass in ("--allow-missing-dev", "--skip-coverage", "--no-dev", "--personal"):
        assert bypass not in source


def test_the_general_trainer_refuses_a_dev_free_dataset(compiled) -> None:
    config = GENERAL.load_config(ROOT / "research" / "lora" / "configs" / "qwen3_8b_qlora.json")
    examples = load_jsonl(compiled["train_path"])

    with pytest.raises(RuntimeError):
        GENERAL.execute(config, examples)


def test_both_trainers_render_the_same_semantic_prompt(compiled) -> None:
    example = load_jsonl(compiled["train_path"])[0]

    assert TRAIN.render_semantic_prompt(example) == GENERAL.render_semantic_prompt(example)


def test_training_rows_are_prompt_completion_pairs(compiled) -> None:
    rows = TRAIN.build_training_rows(load_jsonl(compiled["train_path"]))

    assert all(row["prompt"][0]["role"] == "user" for row in rows)
    assert all(row["completion"][0]["role"] == "assistant" for row in rows)
    assert all(row["split"] == "train" for row in rows)


def test_the_prompt_carries_no_style_instruction(compiled) -> None:
    example = load_jsonl(compiled["train_path"])[0]

    prompt = TRAIN.render_semantic_prompt(example).lower()

    for banned in ("like thomas", "his voice", "author's style", "detector", "human-sounding"):
        assert banned not in prompt
