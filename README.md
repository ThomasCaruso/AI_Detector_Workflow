# AI Detector Workflow / AuthorshipShift

A local-first research harness for studying how machine-generated prose changes under document-level transformations while **preserving meaning, factual fidelity, and writing quality**.

Commercial AI-text detectors are treated as scarce held-out evaluations, not an automatic optimization loop.

## Current version

**v0.7.0**

The project combines local generation/revision experiments with component ablations, content-addressed corpus indexing, stratified holdouts, conservative local-compute estimation, paired statistical confidence analysis, content-addressed provenance, a locked holdout-validation protocol, frozen-candidate integrity checks, and a zero-query decision layer for deciding which variants are worth scarce external validation.

## Research question

> Can machine-generated text undergo substantial distributional and document-level transformation while preserving semantic fidelity and equal-or-better writing quality?

The system keeps three objectives separate:

1. **Semantic fidelity** — claims, qualifications, numbers, causal relationships, and conclusions survive.
2. **Writing quality** — a candidate cannot improve by becoming worse prose.
3. **External detector behavior** — measured only at predetermined milestones.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/RESEARCH_PROTOCOL.md`](docs/RESEARCH_PROTOCOL.md), [`docs/ABLATIONS.md`](docs/ABLATIONS.md), [`docs/DECISION_ENGINE.md`](docs/DECISION_ENGINE.md), [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md), [`docs/CORPUS_AND_COMPUTE.md`](docs/CORPUS_AND_COMPUTE.md), and [`docs/HOLDOUT_PROTOCOL.md`](docs/HOLDOUT_PROTOCOL.md).

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

The split stores the manifest SHA-256 so the development/holdout assignment is tied to an exact corpus state.

## Component ablations

Preview the exact task matrix:

```bash
authorship-shift ablation-plan --corpus corpus --output ablations/v07 --split corpus/split.json
```

Estimate the local model-call upper bound **without running a model**:

```bash
authorship-shift estimate-ablation --corpus corpus --split corpus/split.json --output ablations/v07
```

Run locally:

```bash
authorship-shift ablate --corpus corpus --output ablations/v07 --split corpus/split.json --models "gemma3,qwen3:8b,llama3.1:8b" --judge-model gemma3
```

Cap a session to three new runs:

```bash
authorship-shift ablate --corpus corpus --output ablations/v07 --split corpus/split.json --models "gemma3,qwen3:8b" --max-runs 3
```

Suites resume by default. The default config uses at most five development samples.

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
authorship-shift confidence --suite ablations/v07 --baseline baseline
```

This writes `confidence.json` and `confidence_report.md` with deterministic bootstrap confidence intervals, exact sign tests, paired win rates, and oriented improvements for fidelity, quality, gate survival, structural movement, diversity, and candidate count.

These values are local research diagnostics only; they do not predict a proprietary detector score.

## Zero-query decision engine

After the ablation suite and confidence pass:

```bash
authorship-shift decide --suite ablations/v07 --slots 3
```

The decision engine ranks variants using quality/fidelity-first utility, Pareto efficiency, coverage, structural movement, diversity, and compute cost. It suggests which variants deserve validation slots without querying a detector.

## Locked holdout validation

Once development is finished, lock the exact holdout samples and development-selected variants **before generating holdout results**:

```bash
authorship-shift prepare-holdout \
  --corpus corpus \
  --development-suite ablations/v07 \
  --split corpus/split.json \
  --output holdout/v07 \
  --slots 3
```

Verify the lock:

```bash
authorship-shift check-holdout --lock holdout/v07/holdout_lock.json
```

Run only the locked validation matrix:

```bash
authorship-shift run-holdout \
  --lock holdout/v07/holdout_lock.json \
  --models "gemma3,qwen3:8b" \
  --judge-model gemma3
```

The lock fingerprints the source split, development decision, selected variants, and every holdout text. If any of those change, validation refuses to run. The baseline is automatically included for paired held-out comparison. External detector budgets remain zero throughout this phase.

## Tamper-evident experiment records

New experiments store SHA-256 fingerprints for the source, configuration, every candidate, and frozen candidates. External-result records are bound to the exact frozen candidate hash.

Audit one experiment:

```bash
authorship-shift audit --target experiments/product_distribution
```

Audit a full ablation suite:

```bash
authorship-shift audit --target ablations/v07 --suite
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
index + validate corpus
        ↓
stratified development/holdout split
        ↓
local compute estimate
        ↓
component ablations
        ↓
integrity audit
        ↓
paired confidence analysis
        ↓
zero-query decision engine
        ↓
LOCK decision + holdout texts
        ↓
held-out local validation
        ↓
scarce external evaluation
```

## Scope

This is a detector-robustness and distribution-shift research project. Detector scores do not prove or disprove human authorship. Do not use the project to misrepresent authorship where disclosure is required by an institution, publisher, employer, or platform.

## License

MIT.
