from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .ablation import build_ablation_plan, run_ablation_suite, write_ablation_plan, write_ablation_report
from .claim_diff import claim_coverage_report
from .confidence import analyze_confidence, write_confidence_report
from .corpus import split_directory
from .decision import analyze_suite, write_decision_report
from .diversity import summarize_diversity
from .experiment import Experiment
from .metrics import measure, structural_distance
from .models import Candidate, ExternalResult, read_json
from .pipeline import run_pipeline
from .provenance import audit_experiment, audit_suite, write_integrity_report
from .providers import OllamaProvider, ManualProvider
from .report import write_report


def _load_config(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _configured_variants(config: dict, explicit: str | None) -> str | None:
    if explicit:
        return explicit
    names = config.get("ablation", {}).get("default_variants")
    return ",".join(str(name) for name in names) if names else None


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
    print(json.dumps({"a": measure(a).to_dict(), "b": measure(b).to_dict(), "structural_distance": structural_distance(a, b), "pair_diversity": summarize_diversity([a, b]).to_dict()}, indent=2))


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
    print(f"Frozen: {Experiment(args.experiment).freeze_candidate(args.candidate, note=args.note or '')}")


def cmd_record_external(args):
    exp = Experiment(args.experiment)
    result = ExternalResult(detector=args.detector, detector_version=args.version, label=args.label, score=args.score, notes=args.notes or "", candidate_id=args.candidate)
    print(f"Recorded: {exp.record_external(result)}")


def _ollama_providers(config: dict, args) -> tuple[list[OllamaProvider], OllamaProvider]:
    oc = config.get("ollama", {})
    if getattr(args, "models", None):
        model_names = [m.strip() for m in args.models.split(",") if m.strip()]
    elif getattr(args, "model", None):
        model_names = [args.model]
    else:
        model_names = list(oc.get("models") or [oc.get("model", "gemma3")])
    if not model_names:
        raise ValueError("At least one Ollama model is required")
    base_url = oc.get("base_url", "http://localhost:11434")
    temperature = float(oc.get("temperature", 0.8))
    providers = [OllamaProvider(model=m, base_url=base_url, temperature=temperature) for m in model_names]
    judge_model = getattr(args, "judge_model", None) or oc.get("judge_model") or model_names[0]
    return providers, OllamaProvider(model=judge_model, base_url=base_url, temperature=0.2)


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
    result = run_pipeline(exp, providers, judge_provider=judge, plans_n=int(gen.get("plans", 4)), drafts_per_plan=int(gen.get("drafts_per_plan", 1)), beam_width=int(gen.get("beam_width", 4)), beam_rounds=int(gen.get("beam_rounds", 1)), operators=list(gen.get("operators", [])), operators_per_candidate=int(gen.get("operators_per_candidate", 2)), diversity_weight=float(gates.get("diversity_weight", 0.25)), gates=gates)
    print(f"Generated/evaluated {len(result.candidates)} candidates")
    print("Final beam:", ", ".join(result.beam_ids))


def cmd_status(args):
    print(json.dumps(Experiment(args.experiment).status(), indent=2))


def cmd_report(args):
    print(write_report(args.experiment, args.output))


def cmd_split_corpus(args):
    print(split_directory(args.directory, holdout_fraction=args.holdout, seed=args.seed, output=args.output))


def cmd_ablation_plan(args):
    config = _load_config(args.config)
    variants = _configured_variants(config, args.variants)
    max_samples = args.max_samples if args.max_samples is not None else config.get("ablation", {}).get("max_development_samples")
    plan = build_ablation_plan(args.corpus, variants=variants, split_file=args.split, max_samples=max_samples)
    path = write_ablation_plan(args.output, plan)
    print(path)
    print(f"Planned {plan['task_count']} local runs ({plan['sample_count']} samples x {plan['variant_count']} variants)")


def cmd_ablate(args):
    config = _load_config(args.config)
    variants = _configured_variants(config, args.variants)
    max_samples = args.max_samples if args.max_samples is not None else config.get("ablation", {}).get("max_development_samples")
    providers, judge = _ollama_providers(config, args)
    result = run_ablation_suite(args.corpus, args.output, providers, judge_provider=judge, base_config=config, variants=variants, split_file=args.split, max_samples=max_samples, max_runs=args.max_runs, resume=args.resume)
    print(f"Completed {result['completed_runs']} / {result['planned_runs']} planned runs")
    print(Path(args.output) / "ablation_report.md")


def cmd_ablation_report(args):
    print(write_ablation_report(args.suite, args.output))


def cmd_decide(args):
    report = write_decision_report(args.suite, args.output, slots=args.slots)
    analysis = analyze_suite(args.suite, slots=args.slots)
    print(report)
    print("Suggested validation slots:")
    for row in analysis["recommended_validation_slots"]:
        print(f"  {row['slot']}. {row['variant']} — {row['reason']}")


def cmd_confidence(args):
    report = write_confidence_report(
        args.suite,
        args.output,
        baseline=args.baseline,
        confidence=args.level,
        resamples=args.resamples,
        seed=args.seed,
    )
    analysis = analyze_confidence(
        args.suite,
        baseline=args.baseline,
        confidence=args.level,
        resamples=args.resamples,
        seed=args.seed,
    )
    print(report)
    print(f"Computed paired confidence statistics for {len(analysis['comparisons'])} challengers.")


def cmd_audit(args):
    report = write_integrity_report(args.target, args.output, suite=args.suite)
    audit = audit_suite(args.target) if args.suite else audit_experiment(args.target)
    print(report)
    print(f"Integrity: {'PASS' if audit['ok'] else 'FAIL'}")
    if not audit["ok"]:
        raise RuntimeError("Integrity audit failed; inspect the generated report.")


def build_parser():
    p = argparse.ArgumentParser(prog="authorship-shift")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="Create an experiment")
    s.add_argument("--experiment", required=True); s.add_argument("--source", required=True); s.add_argument("--title", required=True); s.add_argument("--config", default="configs/default.json"); s.set_defaults(func=cmd_init)

    s = sub.add_parser("run", help="Run the chained local pipeline")
    s.add_argument("--experiment", required=True); s.add_argument("--provider", choices=["manual", "ollama"], default="manual"); s.add_argument("--model"); s.add_argument("--models"); s.add_argument("--judge-model"); s.set_defaults(func=cmd_run)

    s = sub.add_parser("metrics"); s.add_argument("file"); s.set_defaults(func=cmd_metrics)
    s = sub.add_parser("compare"); s.add_argument("a"); s.add_argument("b"); s.set_defaults(func=cmd_compare)
    s = sub.add_parser("claim-check"); s.add_argument("--content-lock", required=True); s.add_argument("--candidate", required=True); s.set_defaults(func=cmd_claim_check)
    s = sub.add_parser("add-candidate"); s.add_argument("--experiment", required=True); s.add_argument("--file", required=True); s.add_argument("--stage", default="manual"); s.add_argument("--parent"); s.add_argument("--model"); s.set_defaults(func=cmd_add_candidate)
    s = sub.add_parser("freeze"); s.add_argument("--experiment", required=True); s.add_argument("--candidate", required=True); s.add_argument("--note"); s.set_defaults(func=cmd_freeze)
    s = sub.add_parser("record-external"); s.add_argument("--experiment", required=True); s.add_argument("--detector", required=True); s.add_argument("--version"); s.add_argument("--label", required=True); s.add_argument("--score", type=float); s.add_argument("--candidate", required=True); s.add_argument("--notes"); s.set_defaults(func=cmd_record_external)
    s = sub.add_parser("status"); s.add_argument("--experiment", required=True); s.set_defaults(func=cmd_status)
    s = sub.add_parser("report"); s.add_argument("--experiment", required=True); s.add_argument("--output"); s.set_defaults(func=cmd_report)
    s = sub.add_parser("split-corpus"); s.add_argument("directory"); s.add_argument("--holdout", type=float, default=0.2); s.add_argument("--seed", default="authorship-shift"); s.add_argument("--output"); s.set_defaults(func=cmd_split_corpus)

    s = sub.add_parser("ablation-plan", help="Plan a zero-external-query component ablation suite")
    s.add_argument("--corpus", required=True); s.add_argument("--output", required=True); s.add_argument("--config", default="configs/default.json"); s.add_argument("--split"); s.add_argument("--variants"); s.add_argument("--max-samples", type=int); s.set_defaults(func=cmd_ablation_plan)

    s = sub.add_parser("ablate", help="Run local Ollama ablations without external detector queries")
    s.add_argument("--corpus", required=True); s.add_argument("--output", required=True); s.add_argument("--config", default="configs/default.json"); s.add_argument("--split"); s.add_argument("--variants"); s.add_argument("--max-samples", type=int); s.add_argument("--max-runs", type=int); s.add_argument("--model"); s.add_argument("--models"); s.add_argument("--judge-model"); s.add_argument("--no-resume", dest="resume", action="store_false"); s.set_defaults(func=cmd_ablate, resume=True)

    s = sub.add_parser("ablation-report"); s.add_argument("--suite", required=True); s.add_argument("--output"); s.set_defaults(func=cmd_ablation_report)

    s = sub.add_parser("decide", help="Rank local ablations and allocate scarce validation slots without detector queries")
    s.add_argument("--suite", required=True); s.add_argument("--output"); s.add_argument("--slots", type=int, default=3); s.set_defaults(func=cmd_decide)

    s = sub.add_parser("confidence", help="Compute paired bootstrap intervals and sign tests for local ablations")
    s.add_argument("--suite", required=True); s.add_argument("--output"); s.add_argument("--baseline", default="baseline"); s.add_argument("--level", type=float, default=0.95); s.add_argument("--resamples", type=int, default=2000); s.add_argument("--seed", default="authorship-shift"); s.set_defaults(func=cmd_confidence)

    s = sub.add_parser("audit", help="Verify experiment hashes, frozen candidates, external records, and suite integrity")
    s.add_argument("--target", required=True); s.add_argument("--suite", action="store_true"); s.add_argument("--output"); s.set_defaults(func=cmd_audit)
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
