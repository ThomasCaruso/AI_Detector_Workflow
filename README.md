# AI Detector Workflow / AuthorshipShift

A local-first research harness for studying how machine-generated prose changes under document-level transformations while **preserving meaning, factual fidelity, and writing quality**.

Commercial AI-text detectors are treated as scarce held-out evaluations, not an automatic optimization loop.

## Current version

**v0.8.0**

The project combines local generation/revision experiments with component ablations, content-addressed corpus indexing, stratified holdouts, conservative compute estimation, **measured per-run model-call accounting**, paired statistical confidence analysis, content-addressed provenance, a tamper-resistant locked holdout protocol, frozen-candidate integrity checks, and a zero-query decision layer for deciding which variants are worth scarce external validation.

## Research question

> Can machine-generated text undergo substantial distributional and document-level transformation while preserving semantic fidelity and equal-or-better writing quality?

The system keeps three objectives separate:

1. **Semantic fidelity** — claims, qualifications, numbers, causal relationships, and conclusions survive.
2. **Writing quality** — a candidate cannot improve by becoming worse prose.
3. **External detector behavior** — measured only at predetermined milestones.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/RESEARCH_PROTOCOL.md`](docs/RESEARCH_PROTOCOL.md), [`docs/ABLATIONS.md`](docs/ABLATIONS.md), [`docs/DECISION_ENGINE.md`](docs/DECISION_ENGINE.md), [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md), [`docs/CORPUS_AND_COMPUTE.md`](docs/CORPUS_AND_COMPUTE.md), [`docs/HOLDOUT_PROTOCOL.md`](docs/HOLDOUT_PROTOCOL.md), and [`docs/SMOKE_TEST.md`](docs/SMOKE_TEST.md).

## Zero-spend development

```text
development external detector queries: 0
milestone external detector budget:      5
```

Ablation and holdout child experiments forcibly set their external budget to **0**.

## Installation

Requires Python 3.11+.

```bash
git clone https://github.com/ThomasCaruso/AI_Detector_Workflow.git
cd AI_Detector_Workflow
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
pip install -e .
```

For tests:

```bash
pip install pytest
pytest -q
```

## One experiment

```bash
authorship-shift init --experiment experiments/product_distribution --source examples/source.txt --title "Product distribution"

authorship-shift run --experiment experiments/product_distribution --provider ollama --models "gemma3,qwen3:8b" --judge-model gemma3

authorship-shift report --experiment experiments/product_distribution
```

Model names are examples; use models installed in your local Ollama environment.

## First empirical smoke test

v0.8 includes a deliberately small preflight corpus and configuration so the first real run can test the complete local workflow before the development corpus is expanded.

```text
3 synthetic source documents
×
3 variants: baseline, planning_revision, full
=
9 local runs
```

The checked-in topology has a conservative upper bound of **123 local model calls** for all nine runs and **41 calls** for the first one-source/three-variant batch. External-detector budget is zero.

Preview and estimate the exact pinned matrix:

```bash
authorship-shift ablation-plan --corpus corpus --output ablations/smoke_v08 --config configs/smoke.json --split configs/smoke_split.json

authorship-shift estimate-ablation --corpus corpus --output ablations/smoke_v08 --config configs/smoke.json --split configs/smoke_split.json
```

Run only the first paired batch initially:

```bash
authorship-shift ablate --corpus corpus --output ablations/smoke_v08 --config configs/smoke.json --split configs/smoke_split.json --models "gemma3,qwen3:8b" --judge-model gemma3 --max-runs 3
```

`configs/smoke_split.json` intentionally puts all three synthetic samples in development so a stale local `corpus/split.json` cannot silently alter the smoke matrix. See [`docs/SMOKE_TEST.md`](docs/SMOKE_TEST.md) for the inspection criteria and resume procedure.

## Build and validate the corpus

Organize samples by genre when possible:

```text
corpus/
  business/
  science/
  history/
  technical/
  narrative/
```

Index every `.txt` sample and lock its content hash:

```bash
authorship-shift index-corpus corpus
```

Validate the manifest:

```bash
authorship-shift validate-corpus --manifest corpus/corpus_manifest.json
```

Create a deterministic genre-and-length-stratified holdout:

```bash
authorship-shift split-corpus corpus --holdout 0.2 --seed v1 --stratify
```

The split stores the manifest SHA-256 so the development/holdout assignment is tied to an exact corpus state. For corpora made entirely of singleton strata, v0.8 deterministically rebalances one sample when necessary so a corpus with at least two samples cannot silently produce an empty development or holdout partition.

Corpus manifests, deterministic split references, and ablation sample identities use portable corpus-relative references in normal same-filesystem layouts. Moving or cloning the project therefore does not change sample identity merely because its parent directory changed.

## Component ablations

Preview the exact task matrix:

```bash
authorship-shift ablation-plan --corpus corpus --output ablations/v08 --split corpus/split.json
```

Estimate the local model-call upper bound **without running a model**:

```bash
authorship-shift estimate-ablation --corpus corpus --split corpus/split.json --output ablations/v08
```

Run locally:

```bash
authorship-shift ablate --corpus corpus --output ablations/v08 --split corpus/split.json --models "gemma3,qwen3:8b,llama3.1:8b" --judge-model gemma3
```

Cap a session to three new runs:

```bash
authorship-shift ablate --corpus corpus --output ablations/v08 --split corpus/split.json --models "gemma3,qwen3:8b" --max-runs 3
```

Suites resume by default. The default config uses at most five development samples.

Each completed run now persists measured `total_model_calls`, per-stage call counts, and wall-clock runtime into its ablation summary. Resumed runs are re-summarized so older `suite_results.json` files can pick up newer instrumentation when the underlying `pipeline_stats.json` exists.

### Registered variants

| Variant | Isolates |
|---|---|
| `baseline` | direct single-model drafting |
| `planning_only` | explicit document planning |
| `generator_diversity` | multiple generator families + diversity selection |
| `planning_revision` | global revision without operators |
| `planning_operators` | operator expansion without global revision |
| `full_no_diversity` | full pipeline without diversity contribution |
| `full` | all components enabled |

## Statistical confidence before external testing

Do not rely on aggregate means alone. Run paired analysis across the same development samples:

```bash
authorship-shift confidence --suite ablations/v08 --baseline baseline
```

This writes `confidence.json` and `confidence_report.md` with deterministic bootstrap confidence intervals, exact sign tests, paired win rates, and oriented improvements for fidelity, quality, gate survival, structural movement, diversity, **measured model calls**, and candidate count.

Wall-clock runtime is reported elsewhere but deliberately excluded from statistical preference because it depends heavily on hardware and current system load.

These values are local research diagnostics only; they do not predict a proprietary detector score.

## Zero-query decision engine

After the ablation suite and confidence pass:

```bash
authorship-shift decide --suite ablations/v08 --slots 3
```

The decision engine ranks variants using quality/fidelity-first utility, Pareto efficiency, coverage, structural movement, diversity, and measured compute cost. Actual `pipeline_stats.json` model-call counts are preferred; candidate count is only a legacy fallback when measured call data is unavailable.

Wall-clock runtime appears in reports but is not included in utility. The engine suggests which variants deserve validation slots without querying a detector.

## Locked holdout validation

Once development is finished, lock the exact holdout samples and development-selected variants **before generating holdout results**:

```bash
authorship-shift prepare-holdout \
  --corpus corpus \
  --development-suite ablations/v08 \
  --split corpus/split.json \
  --output holdout/v08 \
  --slots 3
```

Verify the lock:

```bash
authorship-shift check-holdout --lock holdout/v08/holdout_lock.json
```

Run only the locked validation matrix:

```bash
authorship-shift run-holdout \
  --lock holdout/v08/holdout_lock.json \
  --models "gemma3,qwen3:8b" \
  --judge-model gemma3
```

The lock fingerprints the source split, development decision, selected variants, every holdout text, and the exact execution partition. If the split, decision, a sample, lock metadata, or `holdout_partition.json` changes after locking, validation refuses to run. Immediately before a verified holdout run, the execution partition is reconstructed from the lock rather than trusted as mutable input.

New v0.8 schema-v3 locks store portable relative references when possible, so moving the research package without changing its contents does not invalidate the lock fingerprint. Legacy schema-v2 absolute-path locks remain verifiable. A fresh lock also refuses to reuse a non-empty prior holdout `suite/` directory. The baseline is automatically included for paired held-out comparison. External detector budgets remain zero throughout this phase.

## Tamper-evident experiment records

New experiments store SHA-256 fingerprints for the source, configuration, every candidate, and frozen candidates. External-result records are bound to the exact frozen candidate hash.

Audit one experiment:

```bash
authorship-shift audit --target experiments/product_distribution
```

Audit a full ablation suite:

```bash
authorship-shift audit --target ablations/v08 --suite
```

Legacy experiments remain readable; missing pre-v0.5 hashes are surfaced as warnings instead of being backfilled as if they had existed originally.

## Freeze before external testing

```bash
authorship-shift freeze --experiment experiments/product_distribution --candidate 12ab34cd56ef --note "Milestone 3 full pipeline"
```

Then manually record the result for that exact frozen candidate:

```bash
authorship-shift record-external --experiment experiments/product_distribution --detector "Pangram" --version "4" --candidate 12ab34cd56ef --label "AI Generated" --score 100 --notes "Milestone 1 baseline"
```

Before recording, the repository verifies that the frozen file still exactly matches the candidate. No external detector is called automatically by this repository.

## Recommended research order

```text
small offline smoke preflight
        ↓
3 × 3 local smoke execution
        ↓
expand + index corpus
        ↓
stratified development/holdout split
        ↓
local compute estimate
        ↓
component ablations + measured compute
        ↓
integrity audit
        ↓
paired confidence analysis
        ↓
compute-aware zero-query decision engine
        ↓
LOCK decision + holdout texts + partition
        ↓
held-out local validation
        ↓
scarce external evaluation
```

## Scope

This is a detector-robustness and distribution-shift research project. Detector scores do not prove or disprove human authorship. Do not use the project to misrepresent authorship where disclosure is required by an institution, publisher, employer, or platform.

## License

MIT.
