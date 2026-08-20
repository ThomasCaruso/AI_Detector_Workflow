# Corpus Design and Local Compute Budgeting

v0.6 adds two controls for making local experiments more reliable before any scarce external validation is used.

## Corpus manifests

Index the corpus before splitting it:

```bash
authorship-shift index-corpus corpus
```

This writes `corpus_manifest.json` with one entry per `.txt` sample:

- relative path
- SHA-256 content hash
- inferred genre from the first subdirectory
- short / medium / long length band
- word, sentence, and paragraph counts

Exact duplicate hashes are recorded explicitly.

A useful directory layout is:

```text
corpus/
  business/
  science/
  history/
  technical/
  narrative/
```

The directory name becomes the genre label. Files directly under `corpus/` receive the `unspecified` label.

Validate the manifest at any time:

```bash
authorship-shift validate-corpus --manifest corpus/corpus_manifest.json
```

The validator reports missing files, changed hashes, duplicate manifest paths, exact duplicate content, and very short samples.

## Stratified holdout

A tiny random holdout can accidentally put an entire genre or length regime on only one side of the split. The stratified split groups samples by `(genre, length_band)` first.

```bash
authorship-shift split-corpus corpus --holdout 0.2 --seed v1 --stratify
```

For strata with at least two samples, the splitter keeps at least one example on each side. Singleton strata use the deterministic hash rule. The split stores the corpus-manifest hash so the exact split can be tied back to the indexed corpus state.

## Compute estimator

Before starting a large local ablation suite:

```bash
authorship-shift estimate-ablation \
  --corpus corpus \
  --split corpus/split.json \
  --output ablations/v06
```

The estimator models the pipeline topology without calling an LLM. It calculates conservative upper bounds for:

- content-lock calls
- structure-planning calls
- drafts
- global revisions
- operator revisions
- fidelity-judge calls
- quality-judge calls
- selector calls
- total model calls per variant and across the suite

The estimate is intentionally a model-call bound rather than a fake token, time, or dollar estimate. Actual token throughput varies substantially by local model and hardware.

## Recommended order

```text
index corpus
    ↓
validate corpus
    ↓
create stratified development/holdout split
    ↓
estimate local compute
    ↓
run ablation suite
    ↓
audit suite integrity
    ↓
paired confidence analysis
    ↓
zero-query decision engine
    ↓
held-out validation
    ↓
scarce external evaluation
```

This order is designed to prevent accidental leakage, unbalanced validation, wasted local compute, and premature external-detector testing.
