# AuthorshipShift Engine v2

## Why the architecture changed

The portable Agent Skill remains useful as an interface and writing-quality layer, but the competition/innovation regression case showed that prompt-level instructions alone do not provide enough control over generation behavior.

Across multiple Skill iterations, structural instructions changed the prose but the host model repeatedly returned to similar openings, transition patterns, balanced argument structure, and lexical families. The project therefore now separates two concerns:

1. **portable interface** — the Agent Skill captures user intent, semantic constraints, voice preferences, and output requirements;
2. **generation engine** — a provider-agnostic harness creates independent candidates, records generation settings, measures diversity, applies deterministic prechecks, and supports later model-based fidelity and quality selection.

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

A future generator may be:

- a hosted API model;
- an open-weight model;
- a local inference runtime;
- a fine-tuned model or adapter;
- a manual/offline bridge during development.

No single provider is required by the architecture. A normal end user should not have to install a local model merely to use AuthorshipShift.

## Generation controls

`src/authorship_shift/engine_v2.py` introduces explicit provider-facing controls:

- `temperature`;
- `top_p`;
- `seed`;
- `max_tokens`.

The engine records requested settings. A concrete provider may support all, some, or none of them. This is intentionally different from asking one model response to simulate several alternatives inside a single decoding trajectory.

When a provider supports independent sampling, the engine can request genuinely separate generations and compare them afterward.

## Candidate diagnostics

`src/authorship_shift/candidate_lab.py` adds deterministic metrics that require no external model or commercial detector:

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

These are diagnostics, not a human-authorship classifier. They help answer concrete engineering questions such as:

- Did the candidates actually diverge from one another?
- Did a rewrite preserve exact numbers and distinctive names?
- Did a generation collapse back to repeated sentence openings?
- Did a revision remain too close to source wording?
- Did a supposedly diverse candidate batch actually produce near-duplicates?

## Selection philosophy

The engine deliberately separates **generation**, **diagnostics**, and **selection**.

A high structural distance is not automatically good. A low transition ratio is not automatically good. Lexical diversity is not a proxy for quality. These metrics describe candidate behavior; they should not silently override fidelity, clarity, or user intent.

The intended selection sequence is:

1. reject candidates that lose immutable details or required claims;
2. reject candidates that alter causal direction or certainty;
3. reject candidates that are clearly worse in writing quality;
4. among the surviving candidates, prefer useful diversity rather than near-duplicates;
5. use voice-match evidence when genuine user samples are available.

## Model tuning

Fine-tuning is a later stage, not the next immediate dependency.

Before training anything, the repository should establish:

- a structured evaluation corpus;
- repeatable candidate-generation experiments;
- deterministic diagnostics;
- fidelity gates;
- clear failure labels;
- enough accepted/rejected examples to know what behavior a tuned model should learn.

If tuning becomes justified, the preferred training representation is semantic content paired with multiple valid realizations rather than a simplistic `AI paragraph -> humanized paragraph` mapping. That reduces the risk of learning shallow replacement rules.

## Cost discipline

Commercial authorship-detector calls are not part of routine iteration. They may be recorded as external metadata at major checkpoints, but the engine should make most development decisions from reproducible local metrics, fidelity checks, writing-quality review, and controlled ablations.

The competition/innovation case already demonstrated why this matters: repeated external checks are expensive and provide little engineering signal when several substantially different versions all receive the same label.

## Current implementation status

Implemented:

- portable Agent Skill;
- semantic/fidelity writing method;
- legacy multi-candidate research pipeline;
- provider-agnostic Engine v2 interface;
- explicit generation-control records;
- deterministic candidate diagnostics;
- conservative immutable-detail precheck;
- pairwise candidate-diversity measurement;
- regression tests for the new engine layer.

Next:

1. convert existing manual test history into structured evaluation data;
2. add a zero-cost CLI report for candidate sets;
3. add a manual candidate-ingest path so ChatGPT/Codex generations can be analyzed without an API;
4. define generation profiles and provider capability reporting;
5. run candidate batches across several writing domains before considering fine-tuning.
