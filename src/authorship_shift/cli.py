from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .claim_diff import claim_coverage_report
from .corpus import split_directory
from .diversity import summarize_diversity
from .experiment import Experiment
from .metrics import measure, structural_distance
from .models import Candidate, ExternalResult, read_json
from .pipeline import run_pipeline
from .providers import OllamaProvider, ManualProvider
from .report import write_report


def _load_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def cmd_init(args):
    config = _load_config(args.config)
    source = Path(args.source).read_text(encoding="utf-8")
    exp = Experiment(args.experiment)
    exp.initialize(args.title, source, config)
    print(f"Initialized {args.experiment}")


def cmd_metrics(args):
    text = Path(args.file).read_text(encoding="utf-8")
    print(json.dumps(measure(text).to_dict(), indent=2))


def cmd_compare(args):
    a = Path(args.a).read_text(encoding="utf-8")
    b = Path(args.b).read_text(encoding="utf-8")
    out = {
        "a": measure(a).to_dict(),
        "b": measure(b).to_dict(),
        "structural_distance": structural_distance(a, b),
        "pair_diversity": summarize_diversity([a, b]).to_dict(),
    }
    print(json.dumps(out, indent=2))


def cmd_claim_check(args):
    content_lock = read_json(args.content_lock)
    candidate = Path(args.candidate).read_text(encoding="utf-8")
    print(json.dumps(claim_coverage_report(content_lock, candidate).to_dict(), indent=2))


def cmd_add_candidate(args):
    exp = Experiment(args.experiment)
    text = Path(args.file).read_text(encoding="utf-8")
    cand = Candidate(text=text, stage=args.stage, parent_id=args.parent)
    cand.metadata["metrics"] = measure(text).to_dict()
    if args.model:
        cand.metadata["generator_model"] = args.model
    exp.add_candidate(cand)
    print(cand.id)


def cmd_freeze(args):
    exp = Experiment(args.experiment)
    path = exp.freeze_candidate(args.candidate, note=args.note or "")
    print(f"Frozen: {path}")


def cmd_record_external(args):
    exp = Experiment(args.experiment)
    result = ExternalResult(
        detector=args.detector,
        detector_version=args.version,
        label=args.label,
        score=args.score,
        notes=args.notes or "",
        candidate_id=args.candidate,
    )
    path = exp.record_external(result)
    print(f"Recorded: {path}")


def _ollama_providers(config: dict, args) -> tuple[list[OllamaProvider], OllamaProvider]:
    oc = config.get("ollama", {})
    model_names = []
    if args.models:
        model_names = [m.strip() for m in args.models.split(",") if m.strip()]
    elif args.model:
        model_names = [args.model]
    else:
        model_names = list(oc.get("models") or [oc.get("model", "gemma3")])
    base_url = oc.get("base_url", "http://localhost:11434")
    temperature = float(oc.get("temperature", 0.8))
    providers = [OllamaProvider(model=m, base_url=base_url, temperature=temperature) for m in model_names]
    judge_model = args.judge_model or oc.get("judge_model") or model_names[0]
    judge = OllamaProvider(model=judge_model, base_url=base_url, temperature=0.2)
    return providers, judge


def cmd_run(args):
    exp = Experiment(args.experiment)
    config = read_json(exp.root / "config.json")
    gen = config.get("generation", {})
    gates = config.get("gates", {})
    if args.provider == "ollama":
        providers, judge = _ollama_providers(config, args)
    else:
        manual = ManualProvider(exp.root / "outbox")
        providers, judge = [manual], manual

    result = run_pipeline(
        exp,
        providers,
        judge_provider=judge,
        plans_n=int(gen.get("plans", 4)),
        drafts_per_plan=int(gen.get("drafts_per_plan", 1)),
        beam_width=int(gen.get("beam_width", 4)),
        beam_rounds=int(gen.get("beam_rounds", 1)),
        operators=list(gen.get("operators", [])),
        operators_per_candidate=int(gen.get("operators_per_candidate", 2)),
        diversity_weight=float(gates.get("diversity_weight", 0.25)),
        gates=gates,
    )
    print(f"Generated/evaluated {len(result.candidates)} candidates")
    print("Final beam:", ", ".join(result.beam_ids))


def cmd_status(args):
    exp = Experiment(args.experiment)
    print(json.dumps(exp.status(), indent=2))


def cmd_report(args):
    path = write_report(args.experiment, args.output)
    print(path)


def cmd_split_corpus(args):
    path = split_directory(args.directory, holdout_fraction=args.holdout, seed=args.seed, output=args.output)
    print(path)


def build_parser():
    p = argparse.ArgumentParser(prog="authorship-shift")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="Create an experiment")
    s.add_argument("--experiment", required=True)
    s.add_argument("--source", required=True)
    s.add_argument("--title", required=True)
    s.add_argument("--config", default="configs/default.json")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("run", help="Run the chained local pipeline")
    s.add_argument("--experiment", required=True)
    s.add_argument("--provider", choices=["manual", "ollama"], default="manual")
    s.add_argument("--model", help="Single Ollama model")
    s.add_argument("--models", help="Comma-separated Ollama models for generator diversity")
    s.add_argument("--judge-model", help="Optional separate local judge model")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("metrics", help="Measure one text locally")
    s.add_argument("file")
    s.set_defaults(func=cmd_metrics)

    s = sub.add_parser("compare", help="Compare two texts locally")
    s.add_argument("a")
    s.add_argument("b")
    s.set_defaults(func=cmd_compare)

    s = sub.add_parser("claim-check", help="Run deterministic claim/immutable-item prechecks")
    s.add_argument("--content-lock", required=True)
    s.add_argument("--candidate", required=True)
    s.set_defaults(func=cmd_claim_check)

    s = sub.add_parser("add-candidate", help="Ingest a manually generated candidate")
    s.add_argument("--experiment", required=True)
    s.add_argument("--file", required=True)
    s.add_argument("--stage", default="manual")
    s.add_argument("--parent")
    s.add_argument("--model")
    s.set_defaults(func=cmd_add_candidate)

    s = sub.add_parser("freeze", help="Freeze a candidate before scarce external evaluation")
    s.add_argument("--experiment", required=True)
    s.add_argument("--candidate", required=True)
    s.add_argument("--note")
    s.set_defaults(func=cmd_freeze)

    s = sub.add_parser("record-external", help="Log one scarce external detector test")
    s.add_argument("--experiment", required=True)
    s.add_argument("--detector", required=True)
    s.add_argument("--version")
    s.add_argument("--label", required=True)
    s.add_argument("--score", type=float)
    s.add_argument("--candidate", required=True)
    s.add_argument("--notes")
    s.set_defaults(func=cmd_record_external)

    s = sub.add_parser("status", help="Show experiment counts and external-query budget")
    s.add_argument("--experiment", required=True)
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("report", help="Write a Markdown experiment report")
    s.add_argument("--experiment", required=True)
    s.add_argument("--output")
    s.set_defaults(func=cmd_report)

    s = sub.add_parser("split-corpus", help="Create a deterministic development/holdout split")
    s.add_argument("directory")
    s.add_argument("--holdout", type=float, default=0.2)
    s.add_argument("--seed", default="authorship-shift")
    s.add_argument("--output")
    s.set_defaults(func=cmd_split_corpus)

    return p


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
