from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.lora_data import load_jsonl, validate_dataset


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported training config schema_version")
    if not payload.get("base_model"):
        raise ValueError("training config requires base_model")
    objective = payload.get("objective", {})
    if objective.get("commercial_detector_objective") is not False:
        raise ValueError("commercial_detector_objective must remain false")
    if objective.get("train_on_semantic_plan_to_target") is not True:
        raise ValueError("train_on_semantic_plan_to_target must remain true")
    return payload


def render_semantic_prompt(example) -> str:
    atoms = "\n".join(f"- {item}" for item in example.content_atoms)
    immutables = (
        "\n".join(f"- {item}" for item in example.immutable_details)
        if example.immutable_details
        else "- none"
    )
    qualifications = (
        "\n".join(f"- {item}" for item in example.required_qualifications)
        if example.required_qualifications
        else "- none"
    )
    return f"""Write the requested prose from the semantic plan below.

Task:
{example.instruction}

Content atoms:
{atoms}

Immutable details:
{immutables}

Required qualifications:
{qualifications}

Preserve meaning, certainty, and supplied details. Do not invent factual claims or names."""


def build_training_rows(examples) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for example in examples:
        rows.append(
            {
                "id": example.id,
                "split": example.split,
                "prompt": [
                    {"role": "user", "content": render_semantic_prompt(example)}
                ],
                "completion": [
                    {"role": "assistant", "content": example.target_text}
                ],
            }
        )
    return rows


def dry_run(config: dict[str, Any], examples) -> int:
    report = validate_dataset(examples)
    rows = build_training_rows(examples)
    print(f"dataset_valid={str(report.valid).lower()}")
    print(f"examples={report.example_count}")
    print(
        "splits="
        + ", ".join(f"{name}:{count}" for name, count in report.split_counts.items())
    )
    print(f"base_model={config['base_model']}")
    print(f"output_dir={config['output_dir']}")
    print(f"prepared_prompt_completion_rows={len(rows)}")
    print("mode=dry-run")
    print("model_download=false")
    print("gpu_required=false")
    if report.errors:
        print("errors:")
        for item in report.errors:
            print(f"- {item}")
        return 1
    if report.warnings:
        print("warnings:")
        for item in report.warnings:
            print(f"- {item}")
    print("Add --execute only after the dataset and holdout contract are frozen.")
    return 0


def execute(config: dict[str, Any], examples) -> int:
    report = validate_dataset(examples)
    if not report.valid:
        raise RuntimeError("dataset validation failed; refusing to load or train a model")
    if report.split_counts.get("train", 0) == 0:
        raise RuntimeError("dataset contains no training examples")
    if report.split_counts.get("dev", 0) == 0:
        raise RuntimeError("dataset contains no development examples")
    if report.split_counts.get("holdout", 0) == 0:
        raise RuntimeError("dataset contains no holdout examples; freeze one before training")

    # Heavy imports are deliberately below the explicit --execute boundary.
    import torch
    from datasets import Dataset
    from peft import LoraConfig, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    rows = build_training_rows(examples)
    train_rows = [row for row in rows if row["split"] == "train"]
    dev_rows = [row for row in rows if row["split"] == "dev"]

    quant = config["quantization"]
    compute_dtype = (
        torch.bfloat16
        if torch.cuda.is_available() and torch.cuda.is_bf16_supported()
        else torch.float16
    )
    quantization_config = BitsAndBytesConfig(
        load_in_4bit=bool(quant.get("load_in_4bit", True)),
        bnb_4bit_quant_type=str(quant.get("bnb_4bit_quant_type", "nf4")),
        bnb_4bit_use_double_quant=bool(quant.get("bnb_4bit_use_double_quant", True)),
        bnb_4bit_compute_dtype=compute_dtype,
    )

    model_name = str(config["base_model"])
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        device_map="auto",
        torch_dtype=compute_dtype,
        quantization_config=quantization_config,
    )
    model = prepare_model_for_kbit_training(model)

    lora = config["lora"]
    peft_config = LoraConfig(
        r=int(lora["r"]),
        lora_alpha=int(lora["lora_alpha"]),
        lora_dropout=float(lora["lora_dropout"]),
        target_modules=lora["target_modules"],
        bias=str(lora.get("bias", "none")),
        task_type=str(lora.get("task_type", "CAUSAL_LM")),
    )

    training = config["training"]
    output_dir = str(config["output_dir"])
    args = SFTConfig(
        output_dir=output_dir,
        max_length=int(training["max_length"]),
        learning_rate=float(training["learning_rate"]),
        num_train_epochs=float(training["num_train_epochs"]),
        per_device_train_batch_size=int(training["per_device_train_batch_size"]),
        per_device_eval_batch_size=int(training["per_device_eval_batch_size"]),
        gradient_accumulation_steps=int(training["gradient_accumulation_steps"]),
        gradient_checkpointing=bool(training.get("gradient_checkpointing", True)),
        completion_only_loss=True,
        bf16=compute_dtype == torch.bfloat16,
        fp16=compute_dtype == torch.float16,
        eval_strategy="epoch",
        save_strategy="epoch",
        logging_steps=5,
        seed=int(training["seed"]),
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        processing_class=tokenizer,
        args=args,
        train_dataset=Dataset.from_list(train_rows),
        eval_dataset=Dataset.from_list(dev_rows),
        peft_config=peft_config,
    )
    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"saved_adapter={output_dir}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate or explicitly execute the first AuthorshipShift QLoRA experiment."
    )
    parser.add_argument("dataset", type=Path, help="JSONL corpus following lora_data.py")
    parser.add_argument(
        "--config",
        type=Path,
        default=ROOT / "research" / "lora" / "configs" / "qwen3_8b_qlora.json",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Cross the model-download/GPU boundary and run training",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    examples = load_jsonl(args.dataset)
    return execute(config, examples) if args.execute else dry_run(config, examples)


if __name__ == "__main__":
    raise SystemExit(main())
