# The cross-domain collapse experiment

This is the experiment that established the limit of prompt/profile-only control in AuthorshipShift. Commercial detector scores are secondary validation, not the optimization loop.

## The question

Do independent generations under different writing profiles move into meaningfully different writing distributions, or are the profile effects small relative to ordinary generation-to-generation variation?

Mean pairwise distance cannot answer this. Sampling noise creates spread even when profile labels are decorative. The experiment therefore compares **between-profile dispersion** with **within-profile dispersion**.

## Decision-grade design

```text
5 domains x 5 generation profiles x 4 independent samples per profile
= 100 generations
```

One sample per profile cannot estimate within-profile dispersion. Two samples make the statistic defined, but direct replication showed that **5x2 is not stable enough for a training-direction decision**.

The decisive pilot result was:

| design / round | within | between | ratio | p | reading |
| --- | ---: | ---: | ---: | ---: | --- |
| 5x2, fixed template round 1 | 0.0705 | 0.1058 | 1.500 | 0.0015 | separated |
| 5x2, byte-identical replication | 0.0739 | 0.0865 | 1.171 | 0.0760 | weak |
| pooled 5x4 | — | — | 1.245 | 0.0010 | weak |

The two 5x2 batches used byte-identical prompts but disagreed on the action reading. Their within terms were similar; the between term moved materially. The permutation p-value conditions on the observed texts and does not measure whether a new set of generations will reproduce the same effect. That is why 5x4 became the decision-grade default.

Two samples per profile remain useful for smoke tests or diagnostics. They are no longer the default for architectural decisions.

## Running it

Prepare all five domains:

```bash
python scripts/run_collapse_experiment.py prepare
```

The command now defaults to four samples per profile and writes 100 prompts under `experiments/collapse_suite/`.

To run a smaller diagnostic batch explicitly:

```bash
python scripts/run_collapse_experiment.py prepare --samples-per-profile 2
```

The CLI warns that this is below the replicated decision-grade protocol.

Run each prompt as a **separate** generation in the model surface being tested and save only the prose to its matching path under `outputs/`. Replicate prompts for a profile are byte-identical by design; the differences between their outputs form the within-profile term. Do not request multiple variants in one model response.

Check progress:

```bash
python scripts/run_collapse_experiment.py status --verbose
```

Aggregate:

```bash
python scripts/run_collapse_experiment.py report
```

The report writes `COLLAPSE_REPORT.md` and `collapse_report.json` under the suite root.

## Per-domain measurements

Each domain records:

- between-profile dispersion;
- within-profile dispersion;
- collapse ratio;
- permutation p-value and resolution;
- nearest-neighbour distance and near-duplicate pairs;
- fidelity gate result and evidence class;
- unsupported added-name checks;
- quality-defect reranking and shortlist.

## Magnitude is the decision variable

The predeclared practical separation threshold is **1.25**.

A small effect can become statistically significant with enough samples. That does not make the profile intervention useful. The final experiment demonstrated this directly: several ratios in the weak band had small p-values.

The action policy is therefore magnitude-first:

| Observation | Meaning | Action |
| --- | --- | --- |
| trusted ratio below ~1.05 | profile labels explain no more variation than resampling | collapsed |
| ratio 1.05–1.25 | detectable but practically weak steering | weak |
| ratio >=1.25 | potentially useful profile steering | investigate/replicate before escalating |
| high ratio with failed fidelity/quality | effect may be caused by damaged or differently formatted outputs | does not vote |

A complete 5x4 study earns the **prompt/profile ceiling** verdict when at least four trusted domains are powered, gate-passing, backed by checked fidelity evidence, and every trusted ratio remains below 1.25.

## Final corrected study

The final corrected matrix was:

| Domain | Within | Between | Ratio | p | Gate | Reading |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Technical explanation | 0.0823 | 0.0801 | 0.973 | 0.7091 | pass | collapsed |
| Analytical argument | 0.0648 | 0.0722 | 1.113 | 0.0230 | pass | weak |
| Business analysis | 0.0859 | 0.0962 | 1.120 | 0.0575 | pass | weak |
| Professional writing | 0.0719 | 0.0872 | 1.213 | 0.0020 | fail on length | weak |
| Science summary | 0.0665 | 0.0816 | 1.227 | 0.0010 | pass | weak |

The four trusted domains span 0.973–1.227 with a mean of about 1.11. No uncontaminated domain reaches 1.25. The professional-writing result also sits inside the same weak range after a formatting confound was removed, but its remaining word-count failure keeps it out of the trusted vote.

The conclusion is not that profile directives have zero effect. The conclusion is that their measurable effect is **too small to provide the desired control**.

## Historical confounds that were repaired

The study did not accept the first convenient result. It corrected and reran problems that materially affected interpretation:

- 5x2 instability discovered by direct replication;
- a template-induced business-analysis shift;
- document-furniture differences in professional email outputs;
- false immutable failures from sentence-initial terminology and number spelling;
- `%` versus `percent` surface equivalence;
- vacuous fidelity evidence in the analytical argument case;
- unsupported added company names in generated examples.

Historical outputs and checkpoint documentation are retained so those corrections remain auditable.

## Final action

The prompt/profile experiment is frozen. The next research intervention is an open-weight model with a LoRA/QLoRA adapter, evaluated against a frozen base-model control under the same fidelity and held-out evaluation contract.

Additional prompt-only sampling is not the next experiment unless a genuinely new profile intervention or model surface is introduced.

## Scope

These diagnostics do not identify human or AI authorship and are not a surrogate for any commercial detector. External detector observations, if recorded, remain checkpoint metadata and are never the optimization objective.
