# Component Ablation Protocol

Version 0.3 adds a local ablation engine whose purpose is to answer:

> Which pipeline components actually improve fidelity-preserving structural variation, and which merely add compute?

The suite never calls a commercial detector. Every suite run overrides its external-detector budget to zero.

## Registered variants

| Variant | Planning | Generator pool | Global revision | Operators | Diversity selection |
|---|---|---|---|---|---|
| `baseline` | no | single | no | no | no |
| `planning_only` | yes | single | no | no | no |
| `generator_diversity` | yes | all configured | no | no | yes |
| `planning_revision` | yes | all configured | yes | no | yes |
| `planning_operators` | yes | all configured | no | yes | yes |
| `full_no_diversity` | yes | all configured | yes | yes | no |
| `full` | yes | all configured | yes | yes | yes |

## Workflow

Create the holdout split once:

```bash
authorship-shift split-corpus corpus --holdout 0.2 --seed v1
```

Preview compute:

```bash
authorship-shift ablation-plan --corpus corpus --output ablations/v03
```

Run locally:

```bash
authorship-shift ablate --corpus corpus --output ablations/v03 --models "gemma3,qwen3:8b,llama3.1:8b" --judge-model gemma3
```

Cap compute:

```bash
authorship-shift ablate --corpus corpus --output ablations/v03 --models "gemma3,qwen3:8b" --max-runs 3
```

The suite is resumable by default and writes `suite_plan.json`, `suite_results.json`, `ablation_report.md`, plus one complete experiment directory per sample/variant combination.

## Metrics

The suite aggregates hard-gate pass rate, semantic fidelity, quality delta, structural distance, beam diversity, candidate count, model lineage, and external-query count. These are development diagnostics, not a reconstruction of any proprietary detector.

## External-evaluation boundary

Use local ablations to choose a pipeline, freeze the configuration and held-out protocol, and only then spend scarce external evaluations. Do not use commercial detector results to tune the ablation variants during development.
