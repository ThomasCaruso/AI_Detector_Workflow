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
- candidate count as a rough local compute proxy
- variant coverage across the planned development samples

## Priority order

Fidelity and gate survival receive the largest weights. Writing quality comes next. Structural movement and diversity matter only after the text has survived the content and quality constraints.

A large structural shift cannot compensate for factual drift or degraded prose.

## Pareto frontier

The engine also computes a Pareto frontier. A variant is Pareto-efficient when no other variant is at least as good across every maximized local objective while also using no more candidates, with at least one strict improvement.

This is useful because a single weighted score can hide tradeoffs. The report shows both the utility ranking and Pareto membership.

## Paired comparisons

Ablations are compared on shared sample IDs. For each challenger versus the control baseline, the report gives:

- mean paired delta by metric
- challenger win rate by metric
- number of paired samples

This prevents a variant from looking better merely because it happened to run on easier samples.

## Scarce validation allocation

Run:

```bash
authorship-shift decide --suite experiments/ablation_v1 --slots 3
```

The command writes:

```text
experiments/ablation_v1/decision.json
experiments/ablation_v1/decision_report.md
```

The default slot policy is:

1. include the direct baseline control when it has complete coverage and non-negative quality delta;
2. prefer complete-coverage, non-degrading Pareto-efficient variants;
3. fill any remaining slots by local utility.

The resulting list is a **validation allocation**, not a prediction that any candidate will cross an external detector threshold.

## Why this matters

With a five-query external budget, repeated black-box hill climbing is both expensive and methodologically weak. The local decision layer lets the project run broad component ablations first, reject variants that damage fidelity or quality, and spend scarce external tests only on frozen, preselected approaches.
