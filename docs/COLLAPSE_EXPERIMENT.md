# The cross-domain collapse experiment

This is the central experiment. Commercial detector scores are secondary
validation, not the optimization loop.

## The question

Do genuinely independent model generations, plus sampling and profile variation,
produce materially different prose while preserving semantics? Or does everything
collapse back toward one model writing distribution?

Mean pairwise distance cannot answer this. A batch posts a healthy mean whether
the profile directives do anything or not, because ordinary sampling noise
produces spread on its own. The experiment compares **between-profile**
dispersion against **within-profile** dispersion instead.

## The design

```text
5 domains x 5 generation profiles x 2 independent samples per profile
= 50 generations
```

Two samples per profile is the minimum, not a preference. With one sample per
profile there is no within-profile term at all, and a profile effect cannot be
distinguished from sampling noise.

Five profiles is also load-bearing. Relabeling equal-sized groups reproduces the
same partition and ties with the observed ratio, which puts a floor under the
permutation p-value:

| design | distinct groupings | smallest reachable p |
|---|---|---|
| 3 profiles x 2 samples | 90 | 3!/90 = 0.067 |
| 5 profiles x 2 samples | 113,400 | 5!/113,400 = 0.001 |

A three-by-two batch cannot reach significance however large the real effect is.
**5 x 2 is the minimum adequately powered design and should be used from here
on.**

## Running it

Prepare all five domains:

```bash
python scripts/run_collapse_experiment.py prepare
```

This writes 50 prompts under `experiments/collapse_suite/`, ten per domain. No
API call is made.

Run each prompt as a **separate** generation in whatever model surface you are
testing, and save only the prose to the matching path under that domain's
`outputs/`. The two prompts for a given profile are identical by design; the
difference between their outputs is the within-profile term. Do not shortcut
this by asking one response for two variants — that destroys the measurement.

Check progress at any time:

```bash
python scripts/run_collapse_experiment.py status --verbose
```

`status` exits non-zero while generations are outstanding, so it composes with
shell scripting.

Aggregate:

```bash
python scripts/run_collapse_experiment.py report
```

This prints the table and writes `COLLAPSE_REPORT.md` and
`collapse_report.json` under the suite root. Partial completion is fine; domains
without outputs are reported as not measured rather than silently skipped.

## What is recorded per domain

- between-profile dispersion;
- within-profile dispersion;
- collapse ratio;
- permutation p-value, and whether the design could reach significance at all;
- nearest-neighbour distance and any near-duplicate pairs;
- fidelity gate result and whether the fidelity check had anything to verify;
- quality-defect reranking and the resulting shortlist.

## Reading the result

| Observation | Meaning | Action |
|---|---|---|
| Ratio near 1.0 across domains | Prompts and profiles barely move the distribution relative to sampling variance. The base model dominates. | Move to LoRA or fine-tuning. |
| Ratio above 1.0 with significance, across domains | Profiles genuinely steer the distribution. | Improve generation and reranking before training anything. |
| Strong effect in some domains only | Domain-dependent controllability, which is itself a useful finding. | Scope any tuning to the resistant genres. |
| High ratio but failing fidelity or quality | Technically controllable, but the intervention is damaging the writing. | Not a win. Fix fidelity first, then re-measure. |
| Low mean distance with one or two near-duplicate pairs | A collapse the aggregate mean would have hidden. | The nearest-neighbour gate catches this; inspect the flagged pairs. |

The suite encodes these rules in `collapse_suite.decide`, so the verdict is
reproducible rather than eyeballed across five separate reports.

### One guard worth knowing about

If every measured domain fails the fidelity or length gate, the suite issues no
collapse verdict at all. A ratio computed over candidates that dropped content or
missed the target length says nothing about the model's writing distribution, and
recommending a training programme off such a batch would be the worst outcome
this harness could produce.

## Cost

Zero. Every statistic above is deterministic and computed locally. External
detector observations, if recorded at a checkpoint, remain metadata and are never
the optimization objective.
