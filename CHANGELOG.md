# Changelog

## 0.3.1

- Added per-stage local model-call instrumentation and `pipeline_stats.json`.
- Added wall-clock runtime tracking for every pipeline run.
- Recorded generator/judge identities and active pipeline feature flags with each run.
- Added regression tests for call accounting on both the full beam path and the direct baseline.
- External detector budgets remain unchanged; this instrumentation consumes no detector queries.

## 0.3.0

- Added a first-class component-ablation engine for zero-external-query development.
- Added seven registered variants from direct baseline through the full pipeline.
- Added pipeline feature flags for planning, global revision, operators, and diversity-aware selection.
- Added single-generator versus heterogeneous-generator ablations.
- Added resumable corpus-wide local suites with per-run experiment isolation.
- Added deterministic development-split consumption and held-out protection.
- Added suite-level aggregate metrics and Markdown reports.
- Added compute-budget controls with `--max-samples` and `--max-runs`.
- Ablation runs force their external-detector budget to zero.
- Added ablation documentation and tests.

## 0.2.0

- Added composition-operator beam expansion.
- Added multi-model Ollama generation metadata.
- Added deterministic claim-coverage and immutable-item prechecks.
- Added candidate freezing before external evaluation.
- Added pairwise diversity scoring.
- Added deterministic development/holdout corpus splitting.
- Added Markdown experiment reports.
- Added research-protocol and architecture documentation.
- Added GitHub Actions test workflow.

## 0.1.0

- Initial content-lock, planning, drafting, global revision, fidelity, quality, and selection pipeline.
- Added sparse external-query budget enforcement.
- Added manual and Ollama providers.
