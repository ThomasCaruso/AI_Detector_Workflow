"""Base-vs-adapter holdout evaluation for the personal-style experiment.

Obeys the protocol frozen in ``configs/personal_b_eval_protocol.json`` before the
adapter existed. The protocol is read, never written.

Two modes:

* default - dry run. Validates the entire contract, including prompts, seeds,
  blind labels, and the adapter archive digest, WITHOUT importing torch or
  loading a model. Safe to run anywhere.
* ``--execute`` - generate all 24 outputs, then write the blinded outputs and the
  condition mapping to separate files.

Scoring is not implemented here on purpose. The protocol requires every output to
exist before any scoring begins, so scoring is a separate step against the
blinded file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from authorship_shift.lora_data import load_jsonl
from authorship_shift.personal_eval import (
    CONDITION_ADAPTER,
    CONDITION_BASE,
    ProtocolViolation,
    assert_blinded_records_are_clean,
    assign_blind_labels,
    build_generation_plan,
    load_protocol,
    protocol_sha256,
    split_blinded_outputs,
    verify_plan_contract,
)

DEFAULT_PROTOCOL = ROOT / "research" / "lora" / "configs" / "personal_b_eval_protocol.json"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_adapter_archive(path: Path, protocol: dict[str, Any]) -> str:
    """Refuse to proceed unless the archive is the one bound into the protocol."""

    expected = str(protocol["adapter_artifact_sha256"])
    if not path.exists():
        raise ProtocolViolation(f"adapter archive not found: {path}")
    actual = file_sha256(path)
    if actual != expected:
        raise ProtocolViolation(
            f"adapter archive sha256 {actual} does not match the protocol's frozen "
            f"{expected}; this is not the adapter the protocol was bound to"
        )
    return actual


def _report_common(protocol: dict[str, Any], plan, assignments, examples) -> None:
    generation = protocol["generation"]
    print(f"protocol_id={protocol['protocol_id']}")
    print(f"protocol_sha256={protocol_sha256(protocol)}")
    print(f"base_model={protocol['base_model']}")
    print(f"base_model_revision={protocol['base_model_revision']}")
    print(f"adapter_artifact_sha256={protocol['adapter_artifact_sha256']}")
    print(f"holdout_examples={len(examples)}")
    print(f"conditions={','.join(protocol['conditions'])}")
    print(f"expected_outputs={plan.expected_output_count}")
    print(f"enable_thinking={str(protocol['prompt']['enable_thinking']).lower()}")
    print(f"do_sample={str(generation['do_sample']).lower()}")
    print(f"temperature={generation['temperature']}")
    print(f"top_p={generation['top_p']}")
    print(f"top_k={generation['top_k']}")
    print(f"min_p={generation['min_p']}")
    print(f"max_new_tokens={generation['max_new_tokens']}")
    print(f"num_return_sequences={generation['num_return_sequences']}")
    print(f"repetition_penalty={generation['repetition_penalty']}")
    print(f"evaluation_seed={generation['evaluation_seed']}")
    print(f"blind_seed={protocol['blinding']['blind_seed']}")
    print("example_order=" + ",".join(unit.example_id for unit in plan.units))
    print("per_example_seeds=" + ",".join(f"{u.example_id}:{u.seed}" for u in plan.units))
    print("blind_labels=" + ",".join(a.label for a in assignments))


def dry_run(args, protocol: dict[str, Any]) -> int:
    examples = load_jsonl(args.holdout)
    plan = build_generation_plan(examples, protocol)
    verify_plan_contract(plan, protocol)
    assignments = assign_blind_labels(plan, protocol)

    adapter_state = "not_checked"
    if args.adapter_archive is not None:
        verify_adapter_archive(args.adapter_archive, protocol)
        adapter_state = "verified"

    _report_common(protocol, plan, assignments, examples)
    print(f"adapter_archive={adapter_state}")

    # Prompt identity across conditions, stated explicitly rather than implied.
    prompts = {}
    for task in plan.tasks:
        prompts.setdefault(task.example_id, set()).add(task.prompt)
    print(
        "identical_prompt_per_example="
        + str(all(len(values) == 1 for values in prompts.values())).lower()
    )
    seeds = {}
    for task in plan.tasks:
        seeds.setdefault(task.example_id, set()).add(task.seed)
    print(
        "identical_seed_per_example="
        + str(all(len(values) == 1 for values in seeds.values())).lower()
    )
    print("target_text_in_prompt=false")
    print(f"unique_blind_labels={len({a.label for a in assignments})}")
    print("mode=dry-run")
    print("model_loaded=false")
    print("outputs_generated=0")
    print("scoring_performed=false")
    print("Add --execute on the GPU host to generate all outputs.")
    return 0


def preflight(protocol: dict[str, Any]) -> int:
    """Report whether this machine can run the frozen generation. Downloads nothing.

    The training run proved the value of checking the API surface before renting
    time: the stack resolves to whatever is current on the day, and the protocol
    pins sampling parameters that a newer major version may have renamed or
    dropped. ``min_p`` in particular is a relatively recent addition, and
    ``enable_thinking`` is a Qwen chat-template kwarg rather than a core one.
    """

    import platform

    print(f"os={platform.platform()}")
    print(f"python={platform.python_version()}")

    def version_of(name: str) -> str | None:
        try:
            return getattr(__import__(name), "__version__", "unknown")
        except Exception:
            return None

    torch_version = version_of("torch")
    print(f"torch={torch_version or 'not installed'}")

    cuda_available = False
    if torch_version:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        print(f"cuda_available={str(cuda_available).lower()}")
        print(f"cuda_version={torch.version.cuda or 'none'}")
        if cuda_available:
            print(f"gpu_name={torch.cuda.get_device_name(0)}")
            total = torch.cuda.get_device_properties(0).total_memory
            print(f"gpu_vram_gb={total / (1024 ** 3):.1f}")
            print(f"bf16_supported={str(torch.cuda.is_bf16_supported()).lower()}")
        else:
            print("gpu_name=none")
    else:
        print("cuda_available=false")
        print("gpu_name=none")

    for name in ("transformers", "peft", "accelerate"):
        print(f"{name}={version_of(name) or 'not installed'}")

    # Every sampling parameter the protocol pins must be a field the installed
    # generation stack actually understands. A silently dropped kwarg would mean
    # generating under settings other than the frozen ones.
    unsupported: list[str] = []
    if version_of("transformers"):
        from transformers import GenerationConfig

        config_fields = set(vars(GenerationConfig()))
        for key in ("do_sample", "temperature", "top_p", "top_k", "min_p",
                    "max_new_tokens", "num_return_sequences", "repetition_penalty"):
            supported = key in config_fields
            print(f"supports_{key}={str(supported).lower()}")
            if not supported:
                unsupported.append(key)
    else:
        print("generation_kwargs_checked=false")
        unsupported.append("transformers not installed")

    ok = cuda_available and not unsupported
    print(f"generation_supported={str(ok).lower()}")
    print("model_download=false")
    if unsupported:
        print("blocked_reason=unsupported or unverifiable: " + ", ".join(unsupported))
    if not cuda_available:
        print("blocked_reason=no CUDA device available for generation")
    return 0


def execute(args, protocol: dict[str, Any]) -> int:
    examples = load_jsonl(args.holdout)
    plan = build_generation_plan(examples, protocol)
    verify_plan_contract(plan, protocol)
    assignments = assign_blind_labels(plan, protocol)

    if args.adapter_archive is None:
        raise ProtocolViolation("--adapter-archive is required for --execute")
    verify_adapter_archive(args.adapter_archive, protocol)
    if args.adapter_dir is None:
        raise ProtocolViolation("--adapter-dir is required for --execute")

    # Heavy imports sit below every contract check, so a failed check cannot
    # trigger a model download.
    import torch
    from peft import PeftModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    model_name = str(protocol["base_model"])
    revision = str(protocol["base_model_revision"])
    generation = protocol["generation"]

    tokenizer = AutoTokenizer.from_pretrained(model_name, revision=revision)
    base_model = AutoModelForCausalLM.from_pretrained(
        model_name,
        revision=revision,
        device_map="auto",
        dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
    )
    base_model.eval()

    def generate(model, prompt: str, seed: int) -> str:
        messages = [{"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=bool(protocol["prompt"]["enable_thinking"]),
        )
        inputs = tokenizer(text, return_tensors="pt").to(model.device)
        torch.manual_seed(seed)
        with torch.no_grad():
            out = model.generate(
                **inputs,
                do_sample=bool(generation["do_sample"]),
                temperature=float(generation["temperature"]),
                top_p=float(generation["top_p"]),
                top_k=int(generation["top_k"]),
                min_p=float(generation["min_p"]),
                max_new_tokens=int(generation["max_new_tokens"]),
                num_return_sequences=int(generation["num_return_sequences"]),
                repetition_penalty=float(generation["repetition_penalty"]),
                pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
            )
        completion = out[0][inputs["input_ids"].shape[-1] :]
        return tokenizer.decode(completion, skip_special_tokens=True)

    texts: dict[tuple[str, str], str] = {}

    # Every base output first, then the adapter is attached once. The adapter is
    # never detached and re-attached mid-run, and no output is inspected or
    # regenerated along the way.
    for task in plan.tasks:
        if task.condition == CONDITION_BASE:
            texts[(task.example_id, task.condition)] = generate(
                base_model, task.prompt, task.seed
            )
            print(f"generated condition={CONDITION_BASE} example={task.example_id}")

    adapter_model = PeftModel.from_pretrained(base_model, str(args.adapter_dir))
    adapter_model.eval()
    for task in plan.tasks:
        if task.condition == CONDITION_ADAPTER:
            texts[(task.example_id, task.condition)] = generate(
                adapter_model, task.prompt, task.seed
            )
            print(f"generated condition={CONDITION_ADAPTER} example={task.example_id}")

    if len(texts) != plan.expected_output_count:
        raise ProtocolViolation(
            f"generated {len(texts)} outputs, expected {plan.expected_output_count}"
        )

    blinded, mapping = split_blinded_outputs(assignments, texts)
    assert_blinded_records_are_clean(blinded, assignments)

    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "outputs_blinded.jsonl").write_bytes(
        "".join(
            json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n"
            for record in blinded
        ).encode("utf-8")
    )
    (out_dir / "condition_mapping.json").write_text(
        json.dumps(mapping, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (out_dir / "generation_manifest.json").write_text(
        json.dumps(
            {
                "protocol_id": protocol["protocol_id"],
                "protocol_sha256": protocol_sha256(protocol),
                "base_model": model_name,
                "base_model_revision": revision,
                "adapter_artifact_sha256": protocol["adapter_artifact_sha256"],
                "holdout_examples": len(examples),
                "outputs_generated": len(texts),
                "example_order": [unit.example_id for unit in plan.units],
                "per_example_seed": {unit.example_id: unit.seed for unit in plan.units},
                "generation": {key: generation[key] for key in sorted(generation)},
                "scoring_performed": False,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"outputs_generated={len(texts)}")
    print(f"blinded_outputs={out_dir / 'outputs_blinded.jsonl'}")
    print(f"condition_mapping={out_dir / 'condition_mapping.json'}")
    print("scoring_performed=false")
    print("All outputs exist. Scoring is a separate step against the blinded file.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the frozen base-vs-adapter holdout evaluation. Dry run by default; "
            "--execute loads the model and generates every output."
        )
    )
    parser.add_argument(
        "holdout", type=Path, nargs="?", help="Experiment B holdout JSONL (12 rows)"
    )
    parser.add_argument("--protocol", type=Path, default=DEFAULT_PROTOCOL)
    parser.add_argument("--adapter-archive", type=Path, help="frozen adapter .tar to verify")
    parser.add_argument("--adapter-dir", type=Path, help="extracted adapter directory")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT
        / "research"
        / "lora"
        / "local_corpus"
        / "personal_style"
        / "eval"
        / "personal_b_v1",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Report whether this machine can run the frozen generation. Downloads nothing.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Cross the model-loading boundary and generate all outputs",
    )
    args = parser.parse_args(argv)

    protocol = load_protocol(args.protocol)
    if args.preflight:
        return preflight(protocol)
    if args.holdout is None:
        parser.error("holdout is required unless --preflight is used")
    return execute(args, protocol) if args.execute else dry_run(args, protocol)


if __name__ == "__main__":
    raise SystemExit(main())
