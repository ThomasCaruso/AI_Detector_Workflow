# AI Detector Workflow / AuthorshipShift

A local-first research harness for studying how machine-generated prose changes under document-level transformations while **preserving meaning, factual fidelity, and writing quality**.

Commercial AI-text detectors are treated as scarce held-out evaluations, not an automatic optimization loop.

## Current version

**v0.3.0**

The project supports content locking, multiple document plans, heterogeneous local generators through Ollama, global revision, composition operators, semantic-fidelity and writing-quality gates, deterministic claim checks, diversity-aware beam selection, candidate lineage, candidate freezing, hard external-query budgets, development/holdout splitting, experiment reports, and **component ablation suites across a corpus**.

## Research question

> Can machine-generated text undergo substantial distributional and document-level transformation while preserving semantic fidelity and equal-or-better writing quality?

The system keeps three objectives separate:

1. **Semantic fidelity** — claims, qualifications, numbers, causal relationships, and conclusions survive.
2. **Writing quality** — a candidate cannot improve by becoming worse prose.
3. **External detector behavior** — measured only at predetermined milestones.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md), [`docs/RESEARCH_PROTOCOL.md`](docs/RESEARCH_PROTOCOL.md), and [`docs/ABLATIONS.md`](docs/ABLATIONS.md).

## Zero-spend development

```text
development external detector queries: 0
milestone external detector budget:      5
```

Ablation-suite child experiments forcibly set their external budget to **0**.

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

## v0.3 component ablations

Create a fixed development/holdout split:

```bash
authorship-shift split-corpus corpus --holdout 0.2 --seed v1
```

Preview planned local compute:

```bash
authorship-shift ablation-plan --corpus corpus --output ablations/v03
```

Run locally:

```bash
authorship-shift ablate --corpus corpus --output ablations/v03 --models "gemma3,qwen3:8b,llama3.1:8b" --judge-model gemma3
```

Cap a session to three new runs:

```bash
authorship-shift ablate --corpus corpus --output ablations/v03 --models "gemma3,qwen3:8b" --max-runs 3
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

The suite writes `suite_plan.json`, `suite_results.json`, `ablation_report.md`, and a complete experiment directory for each sample/variant run.

## Freeze before external testing

```bash
authorship-shift freeze --experiment experiments/product_distribution --candidate 12ab34cd56ef --note "Milestone 3 full pipeline"
```

Then manually record the result for that exact frozen candidate:

```bash
authorship-shift record-external --experiment experiments/product_distribution --detector "Pangram" --version "4" --candidate 12ab34cd56ef --label "AI Generated" --score 100 --notes "Milestone 1 baseline"
```

No external detector is called automatically by this repository.

## Development metrics

The project measures fidelity, quality delta, word/sentence/paragraph structure, lexical diversity, repeated n-grams, transition starts, punctuation rates, structural distance, pairwise candidate diversity, claim-recall warnings, immutable-item preservation, and ablation-level aggregate results.

These measurements are **not** presented as reconstructions of Pangram or another proprietary detector.

## Scope

This is a detector-robustness and distribution-shift research project. Detector scores do not prove or disprove human authorship. Do not use the project to misrepresent authorship where disclosure is required by an institution, publisher, employer, or platform.

## License

MIT.
