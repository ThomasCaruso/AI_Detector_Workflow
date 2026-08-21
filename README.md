# AuthorshipShift

AuthorshipShift is a writing-transformation system built around two layers:

1. a **portable ChatGPT/Codex Skill** for semantic locking, voice instructions, and convenient use;
2. a **generation engine** for independent candidate generation, deterministic diagnostics, fidelity checks, and later model tuning.

The Skill is the user-facing interface. The engine is the research and control layer.

## Why the architecture changed

Early versions attempted to do the entire job inside a reusable Agent Skill. Controlled tests showed that the Skill could change structure and wording, but the host model repeatedly returned to similar openings, transition patterns, balanced argument shapes, and lexical families.

That result established an important boundary: prompt instructions can steer generation, but they do not provide direct control over the tokenizer, token probabilities, sampling distribution, or model weights.

AuthorshipShift therefore now separates **instruction-level control** from **generation-level control**.

See [`docs/ENGINE_V2.md`](docs/ENGINE_V2.md) for the current architecture.

## Architecture

```text
source / notes / user request
          |
          v
portable AuthorshipShift Skill
          |
          v
semantic lock + content atoms
          |
          v
Generation Engine v2
     /      |      \
 profile A profile B profile C
     \      |      /
   independent candidates
          |
          v
zero-cost deterministic diagnostics
          |
          v
fidelity + quality gates
          |
          v
candidate selection
          |
          v
finished prose
```

The generator layer is provider-agnostic. It can eventually wrap hosted models, open-weight models, local inference, fine-tuned adapters, or a manual/offline bridge. **A normal end user does not need to download a local model merely to use the portable Skill.**

## Portable Skill

The installable Skill lives at:

```text
.agents/skills/authorship-shift/
├── SKILL.md
└── references/
    ├── CANDIDATE_RERANKING.md
    ├── LEXICAL_RECONSTRUCTION.md
    ├── SELF_CHECK.md
    ├── STRUCTURAL_RECONSTRUCTION.md
    └── WRITING_METHOD.md
```

The Skill handles:

- semantic/content locking;
- preservation of names, dates, figures, citations, and technical terms;
- causal and epistemic fidelity;
- document-level reconstruction;
- voice matching when genuine writing samples are supplied;
- output-mode selection.

### Codex

Open this repository in Codex, or copy `.agents/skills/authorship-shift/` into another project's `.agents/skills/` directory.

### ChatGPT

Where personal Skill upload is supported, zip the `authorship-shift` directory and upload it as a Skill.

If Skill upload is unavailable, use:

```text
portable/CHATGPT_PROMPT.md
```

See [`portable/INSTALL.md`](portable/INSTALL.md).

## Generation Engine v2

The new provider-agnostic interface is implemented in:

```text
src/authorship_shift/engine_v2.py
```

It introduces explicit generation records for:

- temperature;
- top-p;
- seed;
- maximum token budget;
- generation profile;
- provider identity.

A provider may support all, some, or none of those controls. Recording them makes experiments reproducible and creates a clean boundary for later hosted, local, or tuned-model adapters.

The engine deliberately generates a **batch** first and analyzes candidates afterward. This is different from asking one model trajectory to internally pretend that it sampled several alternatives.

## Zero-cost candidate diagnostics

Routine development should not depend on paid external tests.

`src/authorship_shift/candidate_lab.py` measures candidate behavior with deterministic local metrics including:

- sentence-length variation;
- lexical diversity;
- transition-start frequency;
- repeated sentence openings;
- sentence-opening entropy;
- repeated trigrams;
- source/candidate trigram overlap;
- structural distance from the reference;
- conservative immutable-detail coverage;
- pairwise candidate diversity.

These are **diagnostics, not authorship classifiers**. No individual metric is treated as a quality target.

## Distribution-collapse analysis

`src/authorship_shift/collapse.py` addresses the question the project actually
needs answered: do independent generations plus profile and sampling variation
escape the model's writing distribution, or collapse back into it?

Mean pairwise distance cannot tell those apart, because sampling noise produces
spread on its own. The engine instead compares **between-profile** dispersion to
**within-profile** dispersion. A ratio near `1.0` means the profile directives
move candidates no further than resampling the same profile does. The ratio
comes with a seeded permutation test, and the report states when a batch is too
small for that test to reach significance rather than reporting a floor-bound
p-value as evidence of no effect.

This is the project's central experiment, run across all five domains as
`5 domains x 5 profiles x 2 samples = 50 generations`:

```bash
python scripts/run_collapse_experiment.py prepare   # writes 50 prompts, no API call
python scripts/run_collapse_experiment.py status    # what is still outstanding
python scripts/run_collapse_experiment.py report    # aggregate table and verdict
```

The report encodes the decision rules directly, so the verdict is reproducible
rather than eyeballed across five separate reports. If the ratio stays near `1.0`
across domains and providers, prompt- and sampling-level control has reached its
limit, and an open-weight model with LoRA or fine-tuning becomes the next
research direction.

See [`docs/COLLAPSE_EXPERIMENT.md`](docs/COLLAPSE_EXPERIMENT.md) for the full
protocol. A single domain can also be run on its own:

```bash
python scripts/prepare_manual_batch.py business_valuation_001 --samples-per-profile 2
python scripts/analyze_manual_batch.py experiments/manual_batches/business_valuation_001
```

## Candidate reranking

`src/authorship_shift/rerank.py` shortlists candidates that clear the gate. It
scores **defects rather than merit**, so nothing wins by pushing a metric to an
extreme, and it prefers diversity only among candidates of equivalent quality.
Causal/certainty fidelity and voice match still require a judge model or human
review, and the output says so.

Run the current regression corpus with:

```bash
python scripts/analyze_candidate_set.py evals/data/competition_innovation_001.json
```

or emit machine-readable output:

```bash
python scripts/analyze_candidate_set.py evals/data/competition_innovation_001.json --json
```

## Evaluation history

The first live regression case is stored in two forms:

```text
evals/cases/competition_innovation_001.md
evals/data/competition_innovation_001.json
```

The structured file includes the control and Skill v1.0-v1.3 outputs plus external observations supplied during testing. Those external values are recorded as experiment metadata only; they are not treated as ground truth or directly optimized.

The result of that experiment was architectural: repeated prompt-only iteration did not provide enough generation-level control, so development moved into the engine.

## Existing research harness

The earlier Python pipeline remains useful and is not being discarded. It already contains:

- multi-candidate generation;
- beam/diversity selection;
- content locks;
- fidelity and quality judges;
- rewrite operators;
- ablations;
- holdout protocols;
- provenance and compute accounting.

Engine v2 is an extraction and simplification of the parts needed for the next phase, with provider independence and zero-cost candidate analysis as first-class requirements.

Historical documentation remains under `docs/`, including:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/RESEARCH_PROTOCOL.md`](docs/RESEARCH_PROTOCOL.md)
- [`docs/ABLATIONS.md`](docs/ABLATIONS.md)
- [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md)
- [`docs/HOLDOUT_PROTOCOL.md`](docs/HOLDOUT_PROTOCOL.md)

## Fine-tuning roadmap

Fine-tuning is a later step, not a prerequisite for the current engine.

Before training a model or adapter, the project should first accumulate:

1. a multi-domain evaluation corpus;
2. independent candidate batches;
3. deterministic style diagnostics;
4. semantic-fidelity labels;
5. accepted/rejected candidate pairs;
6. evidence that generation controls and reranking alone have reached their limit.

If tuning becomes justified, the preferred training representation is **semantic content paired with multiple valid human realizations**, rather than a simplistic `AI paragraph -> humanized paragraph` mapping.

## Scope

AuthorshipShift is for writing quality, structural and lexical variation, voice matching, semantic preservation, and research into controlled text generation. It does not guarantee a particular result from any AI-writing or authorship detector and should not be used to conceal AI assistance where disclosure is required by a school, employer, publisher, platform, or other institution.

## License

MIT.
