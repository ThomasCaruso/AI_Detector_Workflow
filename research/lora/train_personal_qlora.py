"""Personal-style QLoRA entry point for Experiment B.

Deliberately separate from ``train_qlora.py``. The general five-genre trainer is
decision-grade and requires train/dev/holdout plus full genre x split coverage;
the personal pilot has a different contract and would fail those checks. Adding
a bypass flag to the general trainer would weaken the general experiment for the
convenience of this one, so the two contracts live in two files.

What this trainer requires instead:

* every row is ``split == "train"`` - the holdout file is never opened;
* the dataset bytes hash to the manifest, and the corpus, eligibility-mask and
  annotation-set digests agree across manifest and every row;
* provenance is user-owned and no detector-oriented field is present.

No dev split is required. The pilot's hyperparameters are precommitted and
holdout performance is not used for epoch selection or tuning, so there is
nothing for a dev split to decide. If hyperparameters are tuned later, carve a
document-level dev set out of the training sources rather than tuning against
the frozen holdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.lora_data import load_jsonl, validate_dataset
from authorship_shift.personal_dataset import (
    DEFAULT_EXPERIMENT_ID,
    PERSONAL_PROVENANCE_KIND,
)
from authorship_shift.plan_serialization import (
    SERIALIZER_V1,
    SERIALIZER_V2,
    SERIALIZER_VERSIONS,
    render_v2,
)

DEFAULT_CONFIG = ROOT / "research" / "lora" / "configs" / "qwen3_8b_personal_b_qlora.json"

# Digests that must agree between the manifest and every compiled row.
BOUND_DIGESTS: tuple[str, ...] = (
    "corpus_sha256",
    "eligibility_mask_sha256",
    "annotation_set_sha256",
)


class DatasetContractError(RuntimeError):
    """The dataset does not satisfy the personal-experiment contract."""


def load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported training config schema_version")
    if not payload.get("base_model"):
        raise ValueError("training config requires base_model")
    # A bare model name resolves to whatever "main" points at on the day the pod
    # is rented, so the run would not be reproducible. The personal config pins
    # an exact commit; the general config is a separate contract and unaffected.
    revision = str(payload.get("base_model_revision", "")).strip()
    if not revision:
        raise ValueError(
            "personal training config requires base_model_revision; pin an exact "
            "Hugging Face commit so the base model cannot move under the experiment"
        )
    objective = payload.get("objective", {})
    if objective.get("commercial_detector_objective") is not False:
        raise ValueError("commercial_detector_objective must remain false")
    if objective.get("train_on_semantic_plan_to_target") is not True:
        raise ValueError("train_on_semantic_plan_to_target must remain true")
    return payload


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_train_dataset(
    dataset_path: Path,
    manifest: dict[str, Any],
    examples,
    *,
    expected_experiment_id: str = DEFAULT_EXPERIMENT_ID,
) -> None:
    """Refuse anything that is not the frozen personal training dataset.

    Raises on the first violation. Every check here is a reason to refuse to
    load a model, so they all run before any heavy import.
    """

    if manifest.get("experiment_id") != expected_experiment_id:
        raise DatasetContractError(
            f"manifest experiment_id {manifest.get('experiment_id')!r} != "
            f"{expected_experiment_id!r}"
        )

    actual = file_sha256(dataset_path)
    expected = manifest.get("train_dataset_sha256")
    if actual != expected:
        raise DatasetContractError(
            f"train dataset sha256 {actual} does not match manifest {expected}"
        )

    if not examples:
        raise DatasetContractError("training dataset is empty")

    offending = sorted({row.split for row in examples} - {"train"})
    if offending:
        raise DatasetContractError(
            f"training dataset contains non-train rows: splits {offending}"
        )

    for row in examples:
        if row.provenance.kind != PERSONAL_PROVENANCE_KIND:
            raise DatasetContractError(
                f"{row.id}: provenance.kind {row.provenance.kind!r} is not "
                f"{PERSONAL_PROVENANCE_KIND!r}"
            )
        if row.metadata.get("experiment_id") != expected_experiment_id:
            raise DatasetContractError(
                f"{row.id}: metadata experiment_id "
                f"{row.metadata.get('experiment_id')!r} != {expected_experiment_id!r}"
            )
        for name in BOUND_DIGESTS:
            row_value = row.metadata.get(name)
            manifest_value = manifest.get(name)
            if row_value != manifest_value:
                raise DatasetContractError(
                    f"{row.id}: {name} {row_value} does not match manifest {manifest_value}"
                )

    if manifest.get("train_example_count") != len(examples):
        raise DatasetContractError(
            f"manifest train_example_count {manifest.get('train_example_count')} != "
            f"{len(examples)} rows"
        )

    # Duplicate ids and duplicate target text are caught here as well as by
    # validate_dataset, because both are contract violations rather than
    # dataset-quality warnings.
    seen_ids: set[str] = set()
    seen_targets: dict[str, str] = {}
    for row in examples:
        if row.id in seen_ids:
            raise DatasetContractError(f"duplicate example id {row.id!r}")
        seen_ids.add(row.id)
        previous = seen_targets.get(row.target_sha256)
        if previous is not None:
            raise DatasetContractError(
                f"duplicate target text shared by {previous!r} and {row.id!r}"
            )
        seen_targets[row.target_sha256] = row.id

    report = validate_dataset(examples)
    if not report.valid:
        raise DatasetContractError(
            "dataset validation failed: " + "; ".join(report.errors)
        )


def render_semantic_prompt(example) -> str:
    """Same semantic-plan prompt structure the general trainer uses."""

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


def serializer_version_for(config: dict[str, Any]) -> str:
    """Which prompt layout this run renders, taken solely from the config.

    Absent means ``semantic-plan-v1``: Experiment B and C configs name no
    serializer and must keep rendering the layout their frozen datasets and
    adapters were built against. An unrecognised value fails closed rather than
    falling back, because silently training a different layout than the config
    asked for is the failure this contract exists to prevent.

    Selection is by this field alone. Branching on experiment_id would make the
    layout an implicit property of an experiment's name rather than an explicit
    declaration.
    """

    version = str(config.get("serializer_version", SERIALIZER_V1))
    if version not in SERIALIZER_VERSIONS:
        raise ValueError(
            f"unknown serializer_version {version!r}; supported: {SERIALIZER_VERSIONS}"
        )
    return version


def render_prompt_for(example, serializer_version: str) -> str:
    """Render one example under an explicit layout version.

    v1 delegates to :func:`render_semantic_prompt` unchanged, so the bytes that
    Experiment B and C trained on are produced by the same code that produced
    them, not by a reimplementation that could drift.

    v2 reads ``communicative_function`` from the compiled row's metadata. It is
    never reconstructed from ``instruction``: that mapping is lossy, and a row
    that legitimately lacks a function must render without the field rather than
    acquire an invented one.
    """

    if serializer_version == SERIALIZER_V1:
        return render_semantic_prompt(example)
    if serializer_version == SERIALIZER_V2:
        return render_v2(
            instruction=example.instruction,
            content_atoms=example.content_atoms,
            immutable_details=example.immutable_details,
            required_qualifications=example.required_qualifications,
            communicative_function=(example.metadata or {}).get("communicative_function"),
        )
    raise ValueError(f"unknown serializer_version {serializer_version!r}")


def build_training_rows(examples, *, serializer_version: str = SERIALIZER_V1) -> list[dict[str, Any]]:
    return [
        {
            "id": example.id,
            "split": example.split,
            "prompt": [
                {"role": "user", "content": render_prompt_for(example, serializer_version)}
            ],
            "completion": [{"role": "assistant", "content": example.target_text}],
        }
        for example in examples
    ]


def expected_experiment_id_for(config: dict[str, Any]) -> str:
    """The experiment id the dataset must declare, taken from the config.

    The trainer was written for Experiment B and defaulted to B's id. A later
    experiment ships its own config with its own id, and the dataset contract
    check has to compare against that rather than against B's. Falling back to
    :data:`DEFAULT_EXPERIMENT_ID` keeps a config without an explicit id behaving
    exactly as before.
    """

    return str(config.get("experiment_id", DEFAULT_EXPERIMENT_ID))


def dry_run(config: dict[str, Any], manifest: dict[str, Any], examples, dataset_path: Path) -> int:
    verify_train_dataset(
        dataset_path,
        manifest,
        examples,
        expected_experiment_id=expected_experiment_id_for(config),
    )
    rows = build_training_rows(examples, serializer_version=serializer_version_for(config))
    words = sum(len(example.target_text.split()) for example in examples)

    print("dataset_valid=true")
    print(f"experiment={manifest['experiment_id']}")
    print(f"train_examples={len(examples)}")
    print(f"train_target_words={words}")
    # This trainer has no holdout code path at all; the file is never opened.
    print("holdout_loaded=false")
    print(f"corpus_sha256={manifest['corpus_sha256']}")
    print(f"eligibility_mask_sha256={manifest['eligibility_mask_sha256']}")
    print(f"annotation_set_sha256={manifest['annotation_set_sha256']}")
    print(f"train_dataset_sha256={manifest['train_dataset_sha256']}")
    print(f"base_model={config['base_model']}")
    print(f"base_model_revision={config['base_model_revision']}")
    print(f"output_dir={config['output_dir']}")
    print(f"epochs={int(float(config['training']['num_train_epochs']))}")
    print(f"prepared_prompt_completion_rows={len(rows)}")
    print("eval_strategy=no")
    print("mode=dry-run")
    print("model_download=false")
    print("gpu_required=false")
    print(
        "Add --execute only after --preflight reports 4-bit QLoRA execution is supported."
    )
    return 0


def preflight() -> int:
    """Report whether this machine can run 4-bit QLoRA. Never downloads a model."""

    print(f"os={platform.platform()}")
    print(f"python={platform.python_version()}")

    def version_of(name: str) -> str | None:
        try:
            module = __import__(name)
        except Exception:
            return None
        return getattr(module, "__version__", "unknown")

    torch_version = version_of("torch")
    print(f"torch={torch_version or 'not installed'}")

    cuda_available = False
    supports_bf16 = False
    if torch_version:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        print(f"cuda_available={str(cuda_available).lower()}")
        print(f"cuda_version={torch.version.cuda or 'none'}")
        if cuda_available:
            print(f"gpu_name={torch.cuda.get_device_name(0)}")
            total = torch.cuda.get_device_properties(0).total_memory
            print(f"gpu_vram_gb={total / (1024 ** 3):.1f}")
            supports_bf16 = bool(torch.cuda.is_bf16_supported())
        else:
            print("gpu_name=none")
            print("gpu_vram_gb=none")
        print(f"bf16_supported={str(supports_bf16).lower()}")
    else:
        print("cuda_available=false")
        print("cuda_version=none")
        print("gpu_name=none")
        print("gpu_vram_gb=none")
        print("bf16_supported=false")

    for name in ("bitsandbytes", "transformers", "peft", "trl", "datasets", "accelerate"):
        print(f"{name}={version_of(name) or 'not installed'}")

    missing = [
        name
        for name in ("torch", "transformers", "peft", "trl", "bitsandbytes", "datasets")
        if version_of(name) is None
    ]
    supported = cuda_available and not missing
    print(f"qlora_4bit_supported={str(supported).lower()}")
    print("model_download=false")
    if not supported:
        reasons = []
        if missing:
            reasons.append("missing packages: " + ", ".join(missing))
        if not cuda_available:
            reasons.append(
                "no CUDA device available; 4-bit bitsandbytes QLoRA requires an NVIDIA GPU"
            )
        print("blocked_reason=" + "; ".join(reasons))
        print(
            "This machine cannot run the pilot. Run --preflight on the target GPU host "
            "before --execute. CPU training is not attempted."
        )
    return 0


def execute(config: dict[str, Any], manifest: dict[str, Any], examples, dataset_path: Path) -> int:
    verify_train_dataset(
        dataset_path,
        manifest,
        examples,
        expected_experiment_id=expected_experiment_id_for(config),
    )

    # Heavy imports sit below every contract check, so a rejected dataset can
    # never trigger a model download or GPU initialization.
    import torch
    from datasets import Dataset
    from peft import LoraConfig, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import SFTConfig, SFTTrainer

    rows = build_training_rows(examples, serializer_version=serializer_version_for(config))
    train_rows = [row for row in rows if row["split"] == "train"]
    if len(train_rows) != len(rows):
        raise DatasetContractError("non-train row reached trainer construction")

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
    revision = str(config["base_model_revision"])
    print(f"base_model={model_name}")
    print(f"base_model_revision={revision}")
    tokenizer = AutoTokenizer.from_pretrained(model_name, revision=revision)
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        revision=revision,
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
        gradient_accumulation_steps=int(training["gradient_accumulation_steps"]),
        gradient_checkpointing=bool(training.get("gradient_checkpointing", True)),
        completion_only_loss=True,
        bf16=compute_dtype == torch.bfloat16,
        fp16=compute_dtype == torch.float16,
        # No dev split by design, so there is nothing to evaluate against and no
        # checkpoint may be selected on holdout performance.
        eval_strategy="no",
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
        peft_config=peft_config,
    )
    trainer.train()
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"saved_adapter={output_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate or explicitly execute the personal-style Experiment B QLoRA run. "
            "Separate from the general five-genre trainer by design."
        )
    )
    parser.add_argument("dataset", type=Path, nargs="?", help="Experiment B train JSONL")
    parser.add_argument("--manifest", type=Path, help="Experiment B dataset manifest")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Report whether this machine can run 4-bit QLoRA. Downloads nothing.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Cross the model-download/GPU boundary and run training",
    )
    args = parser.parse_args(argv)

    if args.preflight:
        return preflight()
    if args.dataset is None or args.manifest is None:
        parser.error("dataset and --manifest are required unless --preflight is used")

    config = load_config(args.config)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    examples = load_jsonl(args.dataset)
    if args.execute:
        return execute(config, manifest, examples, args.dataset)
    return dry_run(config, manifest, examples, args.dataset)


if __name__ == "__main__":
    raise SystemExit(main())
