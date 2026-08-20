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

## Batch gate

`src/authorship_shift/batch_gate.py` rejects a candidate batch before scarce external review when basic prerequisites fail. The default gate checks:

- minimum candidate count;
- minimum mean pairwise distance;
- immutable-detail coverage;
- target-length tolerance;
- warnings for repeated openings, transition-heavy prose, and high literal source overlap.

A gate pass does **not** mean that a candidate is human-authored or that a detector will label it in any particular way. It means the batch is diverse and faithful enough to justify deeper evaluation.

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
- manual batch preparation and analysis;
- replay provider for offline candidate ingestion;
- optional OpenAI Responses API generator;
- dry-run-by-default automatic OpenAI batch runner;
- regression tests for the Engine v2 layer and providers.

Next engineering milestones:

1. run the five-profile candidate batch across every seed domain;
2. retain accepted and rejected candidates with failure labels;
3. add quality/fidelity reranking over candidates that pass the deterministic gate;
4. compare provider/model families without changing the evaluation cases;
5. decide from the accumulated evidence whether a tuned open-weight model or adapter is justified.
