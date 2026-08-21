import importlib.util
import json
from pathlib import Path

import pytest

from authorship_shift.lora_data import parse_example


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "research" / "lora" / "train_qlora.py"
SPEC = importlib.util.spec_from_file_location("authorship_shift_train_qlora", MODULE_PATH)
assert SPEC and SPEC.loader
TRAIN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRAIN)


def _example(
    *,
    example_id="fixture-1",
    genre="business_analysis",
    split="train",
    source_id="fixture-doc",
):
    return parse_example(
        {
            "id": example_id,
            "genre": genre,
            "split": split,
            "instruction": "Explain the operating result.",
            "content_atoms": ["revenue increased", "one-time rebate contributed to growth"],
            "immutable_details": ["27%", "2025"],
            "required_qualifications": ["part of the growth was temporary"],
            "target_text": (
                "Revenue rose during 2025, but the headline increase overstates the "
                "underlying operating improvement because part of the gain came from a "
                "temporary rebate. The distinction matters when judging whether the "
                "reported 27% growth rate is likely to describe the business after that "
                f"program expires. Fixture {example_id} keeps this target distinct."
            ),
            "provenance": {"kind": "user_owned", "source_id": source_id},
        }
    )


def _config():
    return {
        "schema_version": 1,
        "base_model": "Qwen/Qwen3-8B",
        "output_dir": "out",
        "objective": {
            "commercial_detector_objective": False,
            "train_on_semantic_plan_to_target": True,
        },
    }


def test_training_config_rejects_detector_objective(tmp_path):
    config = _config()
    config["objective"]["commercial_detector_objective"] = True
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(config), encoding="utf-8")

    try:
        TRAIN.load_config(path)
    except ValueError as exc:
        assert "commercial_detector_objective" in str(exc)
    else:
        raise AssertionError("detector-oriented config should be rejected")


def test_training_rows_use_prompt_completion_structure():
    rows = TRAIN.build_training_rows([_example()])
    assert len(rows) == 1
    assert rows[0]["prompt"][0]["role"] == "user"
    assert rows[0]["completion"][0]["role"] == "assistant"
    assert "Content atoms:" in rows[0]["prompt"][0]["content"]
    assert "27%" in rows[0]["prompt"][0]["content"]


def test_dry_run_never_imports_heavy_training_stack(monkeypatch, capsys):
    blocked = {"torch", "transformers", "datasets", "peft", "trl", "bitsandbytes"}
    original_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in blocked:
            raise AssertionError(f"dry run imported heavyweight dependency {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    rc = TRAIN.dry_run(_config(), [_example()])
    output = capsys.readouterr().out

    assert rc == 0
    assert "mode=dry-run" in output
    assert "model_download=false" in output
    assert "gpu_required=false" in output
    assert "genre_split_coverage=incomplete" in output
    assert "business_analysis:dev" in output


def test_execute_rejects_missing_genre_cells_before_heavy_imports(monkeypatch):
    rows = [
        _example(example_id="train", split="train", source_id="train-doc"),
        _example(example_id="dev", split="dev", source_id="dev-doc"),
        _example(example_id="holdout", split="holdout", source_id="holdout-doc"),
    ]
    blocked = {"torch", "transformers", "datasets", "peft", "trl", "bitsandbytes"}
    original_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name.split(".")[0] in blocked:
            raise AssertionError(f"coverage failure imported heavyweight dependency {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    with pytest.raises(RuntimeError, match="genre x split coverage"):
        TRAIN.execute(_config(), rows)
