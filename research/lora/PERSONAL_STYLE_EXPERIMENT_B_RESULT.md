# Experiment B result — accepted academic voice, first personalized QLoRA pilot

**Status: negative result under this training recipe.** Not a rejection of adapter-based
personalization, and not a rejection of the corpus. The treatment was too small to answer the
question it was pointed at.

This document records aggregate outcomes and the frozen methodology only. Source prose, targets,
generated outputs, per-example scores, and the condition mapping stay local and gitignored.

## Conclusion of record

> Pipeline validated; personalization signal detected at the lexical/register level; overall
> personalization hypothesis not supported under the six-step mixed-corpus training recipe due to
> worse blind style preference and material fidelity regression. Increased target overlap was
> measured but is attributable to supplied immutable details and a flaw in the exclusion filter;
> no memorization evidence was obtained, and none was tested for.

## Frozen contracts

| artifact | commit / digest |
|---|---|
| training implementation | `a2df86c` |
| evaluation protocol precommit | `f3db064` (before the adapter existed) |
| adapter bound into protocol | `48d734f` |
| scoring protocol precommit | `6be4701` (before any generated prose was read) |
| base model | `Qwen/Qwen3-8B` @ `b968826d9c46dd6066d109eabc6255188de91218` |
| corpus | `8ff7b467…3d591d5` |
| eligibility mask | `caf3ce47…268bccb6` |
| annotation set | `039fd751…4392af04` |
| train dataset | `560fb752…2de1bfd4c9` |
| adapter archive | `ec0179f4…3f19ac1de8` |
| frozen score file | `badcc863…08fc47b3b6` |
| scoring manifest | `c7c81a53…0f0a58acd9db9e7a` |

Each stage was frozen before the next could see its inputs: evaluation settings before the adapter
existed, the adapter digest before the holdout was revealed, the scoring rubric before any output
was read, and the score file before the condition mapping was opened.

## Training

| | |
|---|---|
| examples / target words | 37 / 7,853 |
| epochs | 2 |
| batch size × gradient accumulation | 1 × 16 |
| **optimizer steps executed** | **6** |
| LoRA | r=16, α=32, dropout=0.05, all-linear (7 modules) |
| quantization | 4-bit NF4, double quant |
| learning rate / seed | 2e-4 / 20260821 |
| final training loss | 1.825 |
| hardware | NVIDIA A40 48 GB, 67.7 s |

Six optimizer steps is the single most important number here. Two epochs reads like training; at
this corpus size and accumulation it is closer to a pipeline smoke test. Any interpretation of the
result has to carry that caveat.

Training-corpus provenance, which bears on interpretation:

| provenance class | documents | eligible words |
|---|---:|---:|
| `ai_assisted_accepted` (material) | 2 | 3,169 |
| `unclassified` (assistance unknown) | 15 | 4,684 |
| `self_authored` | **0** | **0** |

No document is classified self-authored; provenance was never resolved. Roughly 40% of training
words come from documents known to have had material AI assistance.

## Evaluation

12 held-out examples, never trained on and never present on the training host, generated under both
conditions with identical prompts and identical per-example seeds. 24 outputs, all generated before
any scoring began, blinded as `EVAL-###` and scored against a rubric frozen in advance.

Generation: `enable_thinking=false`, temperature 0.7, top-p 0.8, top-k 20, min-p 0.0,
max_new_tokens 768, one sample per condition per example.

## Primary endpoint — blind paired style preference

| | count |
|---|---:|
| **base wins** | **8** |
| **adapter wins** | **3** |
| ties | 1 |

Exact two-sided sign test on the 11 non-tied pairs: **p = 0.2266**. Reported descriptively; the
decision rule is the win count, not the test.

## Fidelity guardrail — FAILED on both arms

| | base | adapter |
|---|---:|---:|
| mean semantic fidelity (0–10) | 9.25 | **8.00** |
| median | 9.5 | 8.0 |
| hard fails | 0 | **1** |

Adapter mean is **1.25 below** base against a tolerance of 0.5. One adapter output carried
`contradicts_semantic_plan`. Either failure alone triggers the guardrail.

## Classification: no clean signal

Two independent triggers fire: adapter wins (3) do not exceed base wins (8), **and** the fidelity
guardrail fails. This is not a near miss.

## Style dimensions — the informative result

| dimension | base | adapter | Δ |
|---|---:|---:|---:|
| diction and register | 2.17 | 2.42 | **+0.25** |
| overall voice fit | 2.25 | 2.08 | −0.17 |
| sentence rhythm and structure | 2.58 | 2.17 | −0.42 |
| paragraph structure and pacing | 2.58 | 1.92 | **−0.67** |
| rhetorical progression | 2.75 | 2.08 | **−0.67** |

The adapter was not inert. It moved diction and register toward the target — the only dimension it
won — while moving structure and organization away. **The objective appears able to learn surface
voice faster than structural voice.** That asymmetry is the most useful thing this run produced and
is what the next training design has to address.

## Verbosity shift

| | base | adapter | targets |
|---|---:|---:|---:|
| mean words | 242.6 | **302.2** | — |
| median words | 239.0 | 241.5 | — |
| min–max | 150–316 | **160–548** | 139–303 |

Medians are nearly identical while means diverge: the adapter learned to expand on some prompts,
producing a longest output of 548 words against a maximum target of 303. Length behaviour should be
precommitted in future designs so verbosity cannot be mistaken for style learning.

## Verbatim target-overlap diagnostic

Measured at 8-word spans, attributing spans that restate supplied immutable details:

| | raw spans | attributable to supplied details | eligible (unexplained) |
|---|---:|---:|---:|
| base | 12 | 12 | **0** |
| adapter | 23 | 14 | **9** |

The adapter reproduces supplied plan content more literally than base does, consistent with the
verbosity and structure findings. Both remaining adapter spans sit on a boundary between a supplied
immutable detail and adjacent plan content, in 2 of 12 outputs.

**This is not memorization evidence, and cannot be.** The holdout was never in training, so overlap
between an output and a held-out target cannot be recall of that target. Measuring memorization
requires comparing outputs against **training** targets. That test was not performed.

An earlier version of this diagnostic reported base 8 / adapter 17 unexplained spans and was cited
as a memorization concern. That reading was wrong on two counts: the spans were supplied details
being correctly restated, and the exclusion filter was defeated by punctuation differences (an
Oxford comma) and by spans crossing the boundary between two adjacent details. The filter has been
corrected and now reports raw and eligible counts separately so the confusion cannot recur.

## Holdout status: RETIRED for configuration decisions

`learning-portfolio-2`, `nutrition-porject`, `the-soiling-of-old-glory` may remain a diagnostic
dataset but must never again decide a training configuration. Its targets and both conditions'
outputs have been read during scoring, so it can no longer support a blind comparison.

## What this run does and does not establish

Established:

- the end-to-end pipeline works: frozen corpus → deterministic dataset → training → frozen adapter →
  blind evaluation → preregistered decision, with every stage hash-bound;
- the adapter changed model behaviour measurably rather than being inert;
- under this recipe, that change was net-negative on blind style preference and cost fidelity.

Not established, and not tested:

- whether adapter-based personalization works at a credible training scale (6 optimizer steps is too
  weak a treatment to answer it);
- whether `ai_assisted_accepted` prose contaminates the personalization signal;
- whether any memorization of training targets occurs.

## Open questions before the next design

1. Provenance of the 15 `unclassified` documents. The self-authored-vs-mixed ablation cannot be run
   until this is resolved: removing the two known AI-assisted documents today would leave 4,684
   words and would test "smaller corpus", not authorship provenance.
2. Output↔**training**-target overlap under Experiment B.
3. How many genuinely usable words remain once provenance is resolved.
