# AuthorshipShift Engine v2

## Why the architecture changed

The portable Agent Skill remains useful as an interface and writing-quality layer, but the competition/innovation regression case showed that prompt-level instructions alone do not provide enough control over generation behavior.

Across multiple Skill iterations, structural instructions changed the prose but the host model repeatedly returned to similar openings, transition patterns, balanced argument structure, and lexical families. The project therefore separates two concerns:

1. **portable interface** — the Agent Skill captures user intent, semantic constraints, voice preferences, and output requirements;
2. **generation engine** — a provider-agnostic harness creates independent candidates, records generation settings, measures diversity, applies deterministic prechecks, and supports later fidelity and quality selection.

The engine is the research and control layer. The Skill is the convenient front end.

## Target architecture

```text
user request / source
        |
        v
portable AuthorshipShift Skill
        |
        v
semantic lock + content atoms
        |
        v
Generation Engine v2
   |        |        |
   v        v        v
profile A profile B profile C
   |        |        |
 multiple independent candidates
        |
        v
zero-cost deterministic diagnostics
        |
        v
fidelity / quality gates
        |
        v
candidate selection
        |
        v
final prose
```

A generator may be a hosted API model, an open-weight model, a local inference runtime, a tuned model or adapter, or a manual/offline bridge during development. No single provider is required by the architecture.

## Generation controls

`src/authorship_shift/engine_v2.py` records provider-facing requests for:

- `temperature`;
- `top_p`;
- `seed`;
- `max_tokens`.

Support is provider- and model-dependent. Recording a requested setting does not imply that every provider can honor it.

The important architectural change is that candidates can come from **separate generation requests** rather than one response being asked to simulate several alternatives inside a single trajectory.

## OpenAI Responses provider

`src/authorship_shift/providers/openai_responses.py` implements an optional hosted provider for the OpenAI Responses API using Python's standard HTTP library. It does not require the OpenAI Python SDK.

By default it sends only broadly applicable request fields such as `model`, `input`, and `max_output_tokens`. `temperature` and `top_p` are opt-in because support can depend on the selected model. Engine v2 records `seed` for experiment provenance, but this provider does not send a seed parameter.

The automatic runner is deliberately guarded against accidental API spend:

```bash
python scripts/run_engine_v2_openai.py competition_innovation_001 --model <MODEL>
```

Without `--execute`, this is a **dry run**. It prints the number of planned API calls and makes no request.

When you explicitly want to execute a batch:

```bash
export OPENAI_API_KEY="..."
python scripts/run_engine_v2_openai.py competition_innovation_001 \
  --model <MODEL> \
  --candidates-per-profile 2 \
  --execute
```

Only add `--allow-sampling-controls` after verifying that the chosen model accepts `temperature` and `top_p`:

```bash
python scripts/run_engine_v2_openai.py competition_innovation_001 \
  --model <MODEL> \
  --candidates-per-profile 2 \
  --allow-sampling-controls \
  --execute
```

The runner writes the full candidate batch, requested generation settings, deterministic analyses, and batch-gate result under `experiments/engine_v2_openai/` unless another output path is supplied.

## Zero-API path

No API key is required for development. The manual/replay workflow remains first-class:

```bash
python scripts/prepare_manual_batch.py competition_innovation_001
```

Run each generated prompt as a separate ChatGPT/Codex generation, save the outputs in the indicated `outputs/` directory, then analyze the batch:

```bash
python scripts/analyze_manual_batch.py \
  experiments/manual_batches/competition_innovation_001
```

See `docs/MANUAL_BATCH.md` for the complete workflow.

## Generation profiles

`src/authorship_shift/generation_profiles.py` defines five reproducible discourse profiles:

1. direct/plain;
2. mechanism-first;
3. constraint-first;
4. evidence-first;
5. compressed/asymmetric.

Profiles vary discourse organization independently from provider sampling controls. This lets experiments distinguish prompt/profile effects from sampling effects.

## Candidate diagnostics

`src/authorship_shift/candidate_lab.py` provides deterministic metrics that require no external model or commercial detector:

- word and sentence counts;
- sentence-length coefficient of variation;
- lexical diversity;
- transition-start ratio;
- generic sentence-start ratio;
- repeated sentence-opening ratio;
- normalized sentence-opening entropy;
- repeated trigram ratio;
- source/candidate trigram overlap;
- structural distance from the source;
- conservative immutable-detail coverage;
- mean pairwise distance from the other candidates.

These are diagnostics, not a human-authorship classifier. They answer engineering questions such as whether candidates actually diverged, whether numbers were preserved, whether supposedly different generations collapsed into near-duplicates, and whether the rewrite remained too close to source wording.

## Collapse diagnostics

`src/authorship_shift/collapse.py` answers the engine's central research
question: did independent generation plus profile and sampling variation
actually move the output, or did everything fall back into one model writing
distribution?

Mean pairwise distance cannot answer that. A batch posts a healthy mean whether
the profile directives do anything or not, because ordinary sampling noise
produces spread on its own. The statistic that separates those two worlds is the
ratio of **between-profile** dispersion to **within-profile** dispersion:

- ratio near `1.0` — profile directives move candidates no further than
  resampling the same profile does. The profiles are decorative and the model
  distribution dominates.
- ratio well above `1.0` — profiles carve out genuinely different regions.

The ratio is reported with a seeded permutation test over a fixed distance
matrix, in two distance modes: a content-free `stylistic` vector and the
existing `composite` distance. The stylistic mode is the sensitive one, since
candidates in a batch all express the same locked content.

The cross-domain form of this experiment — 5 domains x 5 profiles x 2 samples —
is the project's central experiment. See
[`docs/COLLAPSE_EXPERIMENT.md`](COLLAPSE_EXPERIMENT.md) for the protocol and the
decision rules.

### Replicates are required

Within-profile dispersion needs at least two candidates from the same profile.
A batch of one-sample-per-profile has no within-profile term, and the report
says so instead of guessing:

```bash
python scripts/prepare_manual_batch.py business_valuation_001 --samples-per-profile 2
```

Run every prompt as a separate generation even when two prompts for the same
profile are identical. That identity is the point: the difference between those
two outputs *is* the within-profile term.

### The design reports its own statistical power

Relabeling equal-sized profile groups reproduces the same partition and
therefore ties with the observed ratio, which puts a floor under the p-value:

| design | distinct groupings | smallest reachable p |
|---|---|---|
| 3 profiles x 2 samples | 90 | 3!/90 = 0.067 |
| 5 profiles x 2 samples | 113,400 | 5!/113,400 = 0.001 |

A three-by-two batch cannot produce a significant p-value however large the real
effect is. The report flags such a batch as underpowered and refuses to call a
large effect collapsed on the strength of a p-value the design could never have
produced. **The five-profile, two-sample batch is the smallest adequately
powered design**, which is why it is the recommended default.

## Batch gate

`src/authorship_shift/batch_gate.py` rejects a candidate batch before scarce external review when basic prerequisites fail. The default gate checks:

- minimum candidate count;
- minimum mean pairwise distance;
- minimum nearest-neighbor distance, which catches a near-duplicate pair hiding
  inside an otherwise well-spread batch;
- immutable-detail coverage;
- target-length tolerance;
- warnings for repeated openings, transition-heavy prose, and high literal source overlap.

A gate pass does **not** mean that a candidate is human-authored or that a detector will label it in any particular way. It means the batch is diverse and faithful enough to justify deeper evaluation.

### Fidelity evidence is reported separately from coverage

`immutable_coverage` returns `1.0` when a source exposes no checkable literal
details, which is not the same thing as verified fidelity. The gate therefore
reports `fidelity_evidence` as one of:

- `checked` — every candidate had literal details to verify;
- `partial` — some candidates had none;
- `vacuous` — nothing in the batch was checkable, and the coverage number
  carries no information.

`competition_innovation_001` is a `vacuous` case: its source contains no
numbers or proper names at all. Its gate result says nothing about fidelity, and
the report now states that rather than presenting a clean pass.

## Candidate reranking

`src/authorship_shift/rerank.py` ranks candidates that clear the gate and
shortlists a subset for deeper review.

Because the diagnostics are explicitly not quality targets, the reranker scores
**defects rather than merit**. Each term penalizes a value only for crossing a
threshold in the bad direction and contributes nothing otherwise, so no
candidate can win by pushing a metric to an extreme. Prose with ordinary
transition use scores the same zero as prose with none.

Selection is greedy and deterministic: the cleanest candidate goes first, then
each further slot goes to whichever quality-equivalent candidate sits furthest
from everything already chosen. Diversity breaks ties within an explicit
tolerance; it never outranks quality.

Two stages remain outside the deterministic layer and are named in the output
rather than silently skipped: confirming that causal direction and certainty
survived, and scoring voice match against genuine writing samples.

## Selection philosophy

The engine deliberately separates **generation**, **diagnostics**, and **selection**.

A high structural distance is not automatically good. A low transition ratio is not automatically good. Lexical diversity is not a proxy for quality. The intended selection sequence is:

1. reject candidates that lose immutable details or required claims;
2. reject candidates that alter causal direction or certainty;
3. reject candidates that are clearly worse in writing quality;
4. among the surviving candidates, prefer useful diversity rather than near-duplicates;
5. use genuine voice-match evidence when writing samples are available.

## Model tuning

Model-level tuning is a later stage, not an immediate dependency.

Before training anything, the repository should establish a structured evaluation corpus, repeatable candidate-generation experiments, deterministic diagnostics, fidelity gates, clear failure labels, and enough accepted/rejected examples to know what behavior a tuned model should learn.

If tuning becomes justified, the preferred representation is semantic content paired with multiple valid realizations rather than a simplistic `AI paragraph -> humanized paragraph` mapping. A future tuned generator can plug into the same `ControlledGenerator` interface without replacing the Skill or evaluation harness.

## Cost discipline

Commercial authorship-detector calls are not part of routine iteration. They may be recorded as external metadata at major checkpoints, but normal development should rely on reproducible local metrics, fidelity checks, writing-quality review, controlled generation batches, and ablations.

Likewise, the hosted API runner is dry-run by default. API calls require the explicit `--execute` flag.

## Current implementation status

Implemented:

- portable Agent Skill and fallback prompt;
- structured regression history from Skill v1.0-v1.3;
- five-domain fictional seed corpus;
- provider-agnostic Engine v2 interface;
- explicit generation-control records;
- five reproducible discourse profiles;
- deterministic candidate diagnostics;
- conservative immutable-detail precheck;
- pairwise candidate-diversity measurement;
- batch gating before deeper review;
- manual batch preparation and analysis, with configurable samples per profile;
- replay provider for offline candidate ingestion;
- optional OpenAI Responses API generator;
- dry-run-by-default automatic OpenAI batch runner;
- between-profile versus within-profile collapse diagnostics with a permutation
  test that reports its own statistical power;
- deterministic defect-based reranking and diversity-aware shortlisting;
- regression tests for the Engine v2 layer and providers, including an
  end-to-end zero-API run through the replay provider.

- cross-domain collapse orchestrator and aggregate report with an explicit,
  reproducible verdict.

Next engineering milestones:

1. run the 5 x 5 x 2 generation matrix and produce the aggregate collapse table;
2. retain accepted and rejected candidates with failure labels;
3. compare provider/model families on the same evaluation cases, using the
   collapse ratio as the primary comparison statistic;
4. decide from the accumulated evidence whether a tuned open-weight model or
   adapter is justified.

The decision rule for milestone 4 is now concrete. If independent generations
plus profile and sampling variation produce a separation ratio near `1.0` across
domains and providers, prompt- and sampling-level control has reached its limit,
and an open-weight model with LoRA or full fine-tuning becomes the next
research direction.
