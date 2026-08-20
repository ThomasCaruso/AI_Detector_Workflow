# Changelog

## 0.8.0

- Hardened locked-holdout integrity checks so validation detects altered partition metadata in addition to changed source texts and decisions.
- Added relocatable schema-v3 holdout locks that store portable project/corpus references while retaining verification support for legacy absolute-path schema-v2 locks.
- Guaranteed a nonempty stratified holdout whenever a corpus has at least two usable samples, including singleton-strata fallback behavior.
- Persisted measured local model-call totals in ablation summaries instead of relying only on pre-run candidate-count estimates.
- Added measured model calls to paired confidence analysis and compute-aware decision ranking, while retaining estimates as a fallback when measured totals are unavailable.
- Made corpus manifests, deterministic split references, and ablation sample identities portable across clone locations instead of depending on absolute machine paths.
- Made deterministic splitting hash corpus-relative paths rather than only basenames, preventing same-named files in different genre folders from being artificially coupled.
- Added a three-document, three-variant offline smoke harness with a locked 123-call local compute ceiling, zero detector budget, and CI preflight coverage.
- Updated validation and decision documentation for the measured-compute workflow and added regression coverage for the new accounting behavior.
- Synchronized the runtime package version and project metadata at `0.8.0`.
- External detector budgets remain zero for development, ablation, and holdout child runs.

## 0.7.0

- Added a locked held-out validation protocol that separates pipeline selection from validation.
- `prepare-holdout` fingerprints the development decision, source split, selected variants, and every holdout sample before validation.
- Baseline control is automatically retained in the locked validation matrix.
- `check-holdout` detects changed decisions, changed splits, changed/missing holdout texts, and altered lock metadata.
- `run-holdout` runs only the locked local matrix with external-detector budgets forced to zero.
- Holdout runs are resumable and can be capped with `--max-runs`.
- Completed holdout suites automatically produce paired confidence analysis when a baseline and challenger are present.
- Added holdout-protocol documentation and regression tests.

## 0.6.0

- Added content-addressed corpus manifests with genre, length-band, and text metrics.
- Added corpus validation for changed hashes, missing files, exact duplicates, and very short samples.
- Added deterministic genre-and-length-stratified development/holdout splitting.
- Stratified split records now include the exact corpus-manifest SHA-256.
- Added a zero-query local model-call estimator for every ablation variant and complete suites.
- Added `index-corpus`, `validate-corpus`, and `estimate-ablation` CLI commands.
- Added corpus/compute documentation and regression tests.
- External detector behavior remains held out; no detector calls are made by these features.

## 0.5.0

- Added deterministic paired bootstrap confidence intervals for ablation metrics.
- Added exact two-sided sign tests and per-sample challenger win rates.
- Added `confidence` CLI reports that compare every challenger against a fixed baseline.
- Added SHA-256 fingerprints for experiment source text and canonical configuration.
- Added SHA-256 content fingerprints to every candidate.
- Frozen candidates are now hash-verified before an external result can be recorded.
- External result records now store the exact candidate SHA-256 they refer to.
- Added experiment and suite integrity audits with Markdown/JSON reports.
- Ablation suite audits explicitly reject external detector records inside local-development runs.
- Added reproducibility/confidence documentation and regression tests.
- No automatic external detector calls were added; development remains zero-query by design.

## 0.4.0

- Added a zero-query decision engine for ranking local ablation variants before scarce validation.
- Added quality/fidelity-first utility scoring, Pareto-front detection, and coverage penalties.
- Added paired baseline-versus-challenger summaries over matched development samples.
- Added scarce validation-slot allocation and decision reports.

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