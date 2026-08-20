# AI Detector Workflow / AuthorshipShift

A local-first research harness for studying whether machine-generated prose can move across AI-text detector decision boundaries **without sacrificing meaning, factual fidelity, or writing quality**.

The repository is intentionally built around sparse black-box testing. Commercial detector calls are treated as scarce, held-out evaluation events rather than an optimization loop.

## Current version

**v0.2.0**

The project now supports:

- content locking into atomic claims and immutable items
- genuinely different document-level plans
- multiple local generator families through Ollama
- global document revision
- composition-operator beam expansion
- deterministic claim/immutable-item prechecks
- independent semantic-fidelity judging
- independent writing-quality judging
- pairwise lexical + structural diversity scoring
- candidate lineage and model metadata
- candidate freezing before detector tests
- hard external-query budgets
- deterministic development/holdout corpus splitting
- Markdown experiment reports
- GitHub Actions tests

## Research question

> Can machine-generated text undergo substantial distributional and document-level transformation while preserving semantic fidelity and equal-or-better writing quality?

The project keeps three objectives separate:

1. **Semantic fidelity** — claims, qualifications, numbers, causal relationships, and conclusions survive.
2. **Writing quality** — a candidate may not improve detector behavior by becoming worse prose.
3. **External detector behavior** — measured only at predetermined milestones.

A lower detector score is never allowed to compensate for factual drift or degraded writing.

## Architecture

```text
SOURCE / IDEA
    |
    v
CONTENT LOCK
    |
    v
MULTIPLE DOCUMENT PLANS
    |
    v
HETEROGENEOUS LOCAL GENERATORS
    |
    v
GLOBAL DOCUMENT REVISIONS
    |
    +--> DETERMINISTIC CLAIM PRECHECK
    |
    +--> SEMANTIC FIDELITY JUDGE ---- reject on drift
    |
    +--> QUALITY JUDGE -------------- reject on regression
    |
    v
QUALITY/FIDELITY/DIVERSITY BEAM
    |
    v
COMPOSITION OPERATORS
    |
    +--> re-judge / re-gate
    |
    v
FROZEN MILESTONE CANDIDATES
    |
    v
SCARCE EXTERNAL DETECTOR TESTS
```

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and [`docs/RESEARCH_PROTOCOL.md`](docs/RESEARCH_PROTOCOL.md).

## Why this is not a basic paraphraser

The pipeline deliberately avoids typo injection, synonym roulette, Unicode tricks, character substitutions, sentence scrambling, and other transformations that reduce quality.

The main experimental variables are higher-level:

- information order
- paragraph function
- causal or argumentative progression
- qualification placement
- compression versus expansion
- generator family
- reviser family
- document-level composition operators

Local metrics are explicitly treated as **diagnostics, not a reconstruction of Pangram or another proprietary detector**.

## Zero-spend development

The default configuration allows:

```text
development external detector queries: 0
milestone external detector budget:      5
```

The software will not call Pangram automatically.

### Local inference with Ollama

Install Ollama separately and pull any local models you want to compare. The project talks to Ollama through its local `/api/chat` endpoint.

Example with one model:

```bash
authorship-shift run \
  --experiment experiments/product_distribution \
  --provider ollama \
  --model gemma3
```

Example with several local generator families:

```bash
authorship-shift run \
  --experiment experiments/product_distribution \
  --provider ollama \
  --models "gemma3,qwen3:8b,llama3.1:8b" \
  --judge-model gemma3
```

Candidate metadata records which model generated and revised each version.

> Model names above are examples. Use models that actually exist in your local Ollama installation and fit your hardware.

### Manual mode

Manual mode writes prompt packets into the experiment `outbox/` instead of making paid API calls. Because a chained run requires responses between stages, manual mode is best used stage-by-stage rather than as a one-command unattended run.

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

macOS/Linux:

```bash
source .venv/bin/activate
pip install -e .
```

For development/tests:

```bash
pip install pytest
pytest -q
```

## Quick start

### 1. Create an experiment

```bash
authorship-shift init \
  --experiment experiments/product_distribution \
  --source examples/source.txt \
  --title "Product distribution"
```

### 2. Run locally

```bash
authorship-shift run \
  --experiment experiments/product_distribution \
  --provider ollama \
  --model gemma3
```

The pipeline writes:

```text
experiment/
├── source.txt
├── config.json
├── manifest.json
├── content_lock.json
├── plans.json
├── ranking.json
├── selection.json
├── candidates/
├── frozen/
├── external/
└── outbox/
```

### 3. Check status

```bash
authorship-shift status --experiment experiments/product_distribution
```

### 4. Generate a report

```bash
authorship-shift report --experiment experiments/product_distribution
```

This writes `report.md` inside the experiment.

## Local inspection commands

Measure a text:

```bash
authorship-shift metrics examples/source.txt
```

Compare two versions:

```bash
authorship-shift compare baseline.txt candidate.txt
```

Run deterministic claim checks after a content lock exists:

```bash
authorship-shift claim-check \
  --content-lock experiments/product_distribution/content_lock.json \
  --candidate candidate.txt
```

The claim checker is deliberately conservative in what it claims. It is a lexical/immutable-item warning layer, **not semantic proof**.

## Ingest manually generated candidates

```bash
authorship-shift add-candidate \
  --experiment experiments/product_distribution \
  --file candidate.txt \
  --stage manual_generation \
  --model "model-or-method-name"
```

The command returns a candidate ID.

## Freeze before external testing

External evaluation is freeze-enforced by default.

```bash
authorship-shift freeze \
  --experiment experiments/product_distribution \
  --candidate 12ab34cd56ef \
  --note "Milestone 3 full pipeline"
```

A copy of the exact text is written under `frozen/` and the candidate metadata records the freeze timestamp.

## Record a scarce Pangram test

After testing that exact frozen text manually:

```bash
authorship-shift record-external \
  --experiment experiments/product_distribution \
  --detector "Pangram" \
  --version "4" \
  --candidate 12ab34cd56ef \
  --label "AI Generated" \
  --score 100 \
  --notes "Milestone 1 baseline"
```

The experiment manifest increments `external_queries_used`. Once the configured budget is exhausted, additional results are rejected.

## Recommended five-test protocol

| Test | Candidate |
|---|---|
| 1 | Untouched baseline generation |
| 2 | Best single-stage natural-writing candidate |
| 3 | Best full multi-stage candidate |
| 4 | Winning pipeline on an unseen topic/genre |
| 5 | Frozen blind-validation document |

A method is not considered successful because one document crosses one detector threshold.

## Composition operators

`skills/operators/` contains document-level operators used during beam expansion:

- `claim_first`
- `mechanism_first`
- `contrast_driven`
- `compressed_reasoning`
- `asymmetric_structure`
- `evidence_then_judgment`

Each operator must preserve the content lock and is re-evaluated for semantic fidelity and writing quality before it can survive the beam.

## Beam selection

The local beam uses:

1. semantic fidelity as a hard gate
2. writing-quality delta as a hard gate
3. immutable-item preservation as a hard gate
4. pairwise candidate diversity as a tiebreaking/search term

It does **not** use a commercial detector score.

This is intentional. If Pangram were queried after every rewrite, the project would quickly become an overfit black-box hill climber and the final result would say little about generalization.

## Corpus holdout

Put `.txt` research samples in `corpus/`, then create a deterministic split:

```bash
authorship-shift split-corpus corpus --holdout 0.2 --seed v1
```

This writes `split.json` containing development and held-out samples. Freeze the split before final validation.

## Local metrics

Current descriptors include:

- word, sentence, and paragraph counts
- lexical diversity
- sentence-length mean and coefficient of variation
- paragraph-length mean and coefficient of variation
- short/long sentence ratios
- repeated trigram ratio
- transition-start ratio
- semicolon and em-dash rates
- structural distance between two texts
- pairwise lexical/structural candidate diversity
- claim lexical-recall warnings
- exact immutable-item preservation

Again: **these are development measurements, not a Pangram surrogate**.

## Skills

The writing/evaluation chain lives under `skills/`:

1. `01_content_lock.md`
2. `02_structure_planner.md`
3. `03_draft_writer.md`
4. `04_global_reviser.md`
5. `05_fidelity_judge.md`
6. `06_quality_judge.md`
7. `07_selector.md`
8. `08_operator_rewriter.md`

Keeping them separate makes ablation experiments possible. You can measure whether gains come from planning, generator diversity, global revision, a particular composition operator, or interactions among stages.

## Project structure

```text
.
├── .github/workflows/test.yml
├── configs/default.json
├── corpus/
├── docs/
├── examples/
├── skills/
│   └── operators/
├── src/authorship_shift/
├── tests/
├── CHANGELOG.md
├── LICENSE
├── README.md
└── pyproject.toml
```

## Scope

This is a detector-robustness and distribution-shift research project. It does not claim that detector scores prove or disprove human authorship. It also does not claim that local stylometric metrics predict any proprietary detector.

Do not use the project to misrepresent authorship where disclosure is required by an institution, publisher, employer, or platform.

## License

MIT.
