# v0.8 Local Smoke Test

This is the first empirical execution checkpoint for AuthorshipShift v0.8. It is intentionally small: three synthetic source documents, three pipeline variants, two local generator families, and zero external-detector queries.

## Purpose

The smoke test is not intended to establish detector robustness or select a final pipeline. Its job is to expose failures in generation, judging, gating, accounting, resumability, and report generation before the corpus is expanded.

The three source documents are intentionally information-dense and synthetic. They contain numbers, qualifications, causal distinctions, and uncertainty that the fidelity system must preserve.

## Matrix

```text
3 source documents
×
3 variants
=
9 planned local runs
```

Variants:

```text
baseline
planning_revision
full
```

The smoke config reduces planning and beam width to keep local compute modest while still exercising the major stages.

With the checked-in `configs/smoke.json`, the conservative model-call upper bounds are:

```text
baseline             5 calls/run
planning_revision   15 calls/run
full                21 calls/run
-------------------------------
one-source batch    41 calls
full 3-source run  123 calls
```

These are topology-based upper bounds, not token or wall-clock estimates. The regression suite locks these expectations so accidental compute growth is visible.

## 1. Install and confirm local models

```powershell
pip install -e .
ollama list
```

The checked-in smoke config expects:

```text
gemma3
qwen3:8b
```

If those exact models are not installed, pass available model names with `--models` and select an installed judge with `--judge-model`.

## 2. Index and validate the three-sample corpus

```powershell
authorship-shift index-corpus corpus
authorship-shift validate-corpus --manifest corpus/corpus_manifest.json
```

Do not create the locked development/holdout split yet. With only three samples, the smoke test should exercise all three documents. The real stratified holdout is created only after the corpus is expanded.

## 3. Preview the exact smoke matrix

```powershell
authorship-shift ablation-plan `
  --corpus corpus `
  --output ablations/smoke_v08 `
  --config configs/smoke.json
```

Expected plan:

```text
3 samples × 3 variants = 9 local runs
```

Tasks are deliberately grouped by source, then variant. The first three tasks therefore compare `baseline`, `planning_revision`, and `full` on the same document. A regression test protects this ordering because the first bounded batch is intended to be a paired diagnostic.

## 4. Estimate compute before generation

```powershell
authorship-shift estimate-ablation `
  --corpus corpus `
  --output ablations/smoke_v08 `
  --config configs/smoke.json
```

This consumes no model calls and no detector queries. The expected full-suite upper bound is **123 local model calls**. If the estimate materially differs, inspect the configuration or pipeline topology before generating anything.

## 5. Run only the first three jobs initially

```powershell
authorship-shift ablate `
  --corpus corpus `
  --output ablations/smoke_v08 `
  --config configs/smoke.json `
  --models "gemma3,qwen3:8b" `
  --judge-model gemma3 `
  --max-runs 3
```

Those three runs are the three variants on one source and have a combined conservative ceiling of **41 local model calls**.

Inspect those outputs before continuing. Specifically check for missing claims, altered numbers, unsupported additions, changed certainty, evaluator failures, malformed JSON, quality regressions, and obviously unreasonable model-call accounting.

## 6. Resume the remaining jobs

If the first three runs look structurally sound, rerun the same command without `--max-runs`:

```powershell
authorship-shift ablate `
  --corpus corpus `
  --output ablations/smoke_v08 `
  --config configs/smoke.json `
  --models "gemma3,qwen3:8b" `
  --judge-model gemma3
```

The suite resumes rather than restarting completed work.

## 7. Audit and summarize

```powershell
authorship-shift audit --target ablations/smoke_v08 --suite
authorship-shift confidence --suite ablations/smoke_v08 --baseline baseline
authorship-shift decide --suite ablations/smoke_v08 --slots 3
```

Treat the resulting rankings as debugging evidence only. Nine runs across three synthetic documents are too small for a substantive research conclusion.

## Stop conditions

Stop the smoke test and fix the pipeline before expanding the corpus if any of the following occurs repeatedly:

- immutable numbers disappear or change;
- qualifications are strengthened or removed;
- unsupported claims survive the fidelity gate;
- obviously worse prose passes the quality gate;
- judges fail to return parseable results;
- resumed runs overwrite or duplicate completed work;
- measured model-call totals are missing or inconsistent;
- the planned first three tasks are not the three variants on one source;
- the smoke compute estimate exceeds the expected 123-call topology without an intentional configuration change;
- any development child run records an external-detector query budget above zero.

## After the smoke test

Only after the nine-run smoke matrix is stable should the corpus be expanded toward roughly 20–30 samples across multiple genres and lengths. Then re-index the complete corpus, validate it, freeze a deterministic stratified development/holdout split, and begin the full seven-variant development matrix.
