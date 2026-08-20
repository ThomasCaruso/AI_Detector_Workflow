# Zero-Query Decision Engine

The decision engine exists to answer one question before any scarce external detector test is spent:

> Which locally tested pipeline variants have earned a validation slot?

It intentionally does **not** estimate Pangram, GPTZero, Turnitin, or any other proprietary detector score.

## Inputs

The engine consumes `suite_results.json` from an ablation run and uses only local measurements already produced by the project:

- hard-gate survival rate
- semantic-fidelity score
- writing-quality delta
- structural distance from source
- final-beam diversity
- measured local model-call count
- candidate count
- wall-clock runtime for reporting only
- variant coverage across the planned development samples

Completed runs persist `pipeline_stats.json`. New ablation summaries copy `total_model_calls` and `elapsed_seconds` into `suite_results.json`. The decision engine can also read `pipeline_stats.json` directly when an older suite summary does not contain those fields.

For legacy experiments without pipeline instrumentation, candidate count remains a clearly labeled fallback compute signal. It is not treated as equivalent to a model call.

## Priority order

Fidelity and hard-gate survival receive the largest weights. Writing quality comes next. Structural movement and diversity matter only after the text has survived the content and quality constraints.

Measured model-call count now receives a real compute penalty. Candidate count retains a smaller complexity penalty. Wall-clock time is displayed but deliberately excluded from utility because it depends heavily on model size, hardware, thermal state, and concurrent load.

A large structural shift cannot compensate for factual drift or degraded prose.

## Current utility weights

| Objective | Direction | Weight |
|---|---|---:|
| Hard-gate survival | maximize | 0.28 |
| Semantic fidelity | maximize | 0.24 |
| Writing-quality delta | maximize | 0.20 |
| Structural distance | maximize | 0.08 |
| Beam diversity | maximize | 0.04 |
| Measured model calls | minimize | 0.12 |
| Candidate count | minimize | 0.04 |

Coverage multiplies the resulting utility, so a partially completed variant cannot outrank a fully evaluated variant solely because its early samples happened to look favorable.

## Pareto frontier

The engine also computes a Pareto frontier. A variant is Pareto-efficient when no other variant is at least as good across every maximized local objective while using no more model calls or candidates, with at least one strict improvement.

This is useful because a single weighted score can hide tradeoffs. The report shows both the utility ranking and Pareto membership.

## Paired comparisons

Ablations are compared on shared sample IDs. For each challenger versus the control baseline, the report gives:

- mean paired delta by metric
- challenger win rate by metric
- model-call delta, where fewer calls count as a win
- candidate-count delta, where fewer candidates count as a win
- number of paired samples

This prevents a variant from looking better merely because it happened to run on easier samples.

The separate `confidence` command adds deterministic bootstrap intervals and exact sign tests around those paired comparisons.

## Scarce validation allocation

Run:

```bash
authorship-shift decide --suite ablations/v08 --slots 3
```

The command writes:

```text
ablations/v08/decision.json
ablations/v08/decision_report.md
```

The default slot policy is:

1. include the direct baseline control when it has complete coverage and non-negative quality delta;
2. prefer complete-coverage, non-degrading Pareto-efficient variants;
3. fill any remaining slots by local utility.

The resulting list is a **validation allocation**, not a prediction that any candidate will cross an external detector threshold.

## Why this matters

With a small external budget, repeated black-box hill climbing is both expensive and methodologically weak. The local decision layer lets the project run broad component ablations first, reject variants that damage fidelity or quality, measure the actual compute cost of each approach, and spend scarce external tests only on frozen, preselected approaches.
