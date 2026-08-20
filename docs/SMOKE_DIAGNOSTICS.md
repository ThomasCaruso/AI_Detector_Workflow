# Smoke Diagnostics

After local Ollama generation, use the smoke diagnostic instead of manually opening every artifact first.

The diagnostic is intentionally strict about experiment mechanics and conservative about research outcomes.

## First three-run checkpoint

After running the bounded first batch:

```powershell
authorship-shift ablate `
  --corpus corpus `
  --output ablations/smoke_v08 `
  --config configs/smoke.json `
  --split configs/smoke_split.json `
  --models "gemma3,qwen3:8b" `
  --judge-model gemma3 `
  --max-runs 3
```

run:

```powershell
python scripts/check_smoke.py `
  --suite ablations/smoke_v08 `
  --config configs/smoke.json `
  --mode checkpoint
```

The paired checkpoint expects:

```text
baseline             5 calls
planning_revision   15 calls
full                21 calls
----------------------------
total               41 calls
```

It writes:

```text
ablations/smoke_v08/smoke_diagnostic.md
ablations/smoke_v08/smoke_diagnostic.json
```

## Full nine-run smoke suite

After resuming the remaining six runs, execute:

```powershell
python scripts/check_smoke.py `
  --suite ablations/smoke_v08 `
  --config configs/smoke.json `
  --mode full
```

The complete matrix must contain exactly nine run records and exactly **123 measured local model calls** under the checked-in smoke topology.

## Hard failures

The diagnostic returns a nonzero exit code when it finds infrastructure or protocol failures, including:

- missing required smoke runs;
- duplicate sample/variant records;
- smoke plan drift from the checked-in three-sample / three-variant matrix;
- unexpected model-call totals;
- `call_counts` that do not reconcile to `total_model_calls`;
- any external detector query usage;
- any child run whose detector budget was not forced to zero;
- missing run artifacts;
- empty candidate sets or final beams;
- missing or malformed ranking outputs;
- suite summary values that disagree with `pipeline_stats.json`.

Stored absolute `experiment_root` values are not trusted blindly. If a suite has moved to another checkout location, the diagnostic falls back to the canonical `runs/<sample_id>/<variant>` layout.

## Warnings, not failures

Research outcomes are surfaced without pretending they are infrastructure errors. The report warns when:

- no candidate survived all hard gates;
- mean fidelity is zero;
- model identities are missing from a run summary;
- checkpoint mode is run after more than the initial three jobs have completed.

A warning means the smoke harness executed, but the result needs inspection before scaling the corpus. A hard failure means the experiment mechanics themselves are not trustworthy yet.
