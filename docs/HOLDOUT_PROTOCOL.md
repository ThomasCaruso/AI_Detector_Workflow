# Locked Holdout Validation Protocol

The development suite is allowed to influence pipeline selection. The holdout set is not.

v0.7 adds a lock step between those phases so the selected variants, split file, decision file, and exact holdout texts are fingerprinted before holdout generation begins.

## 1. Finish development first

Run the development ablations, confidence analysis, integrity audit, and decision engine before touching the holdout set.

```bash
authorship-shift decide --suite ablations/v07 --slots 3
```

This creates `decision.json`.

## 2. Lock the holdout

```bash
authorship-shift prepare-holdout \
  --corpus corpus \
  --development-suite ablations/v07 \
  --split corpus/split.json \
  --output holdout/v07 \
  --slots 3
```

The lock records:

- SHA-256 of the original development/holdout split
- SHA-256 of the development decision file
- selected variants
- absolute paths and SHA-256 hashes for every holdout sample
- a fingerprint over the complete lock metadata
- an external-detector allowance of zero

The baseline is included automatically so held-out changes can be evaluated against the same control.

If `holdout_lock.json` already exists, preparation refuses to overwrite it. Starting a different holdout protocol requires an explicit new output directory or deliberate deletion of the old lock.

## 3. Verify before running

```bash
authorship-shift check-holdout --lock holdout/v07/holdout_lock.json
```

The check fails if the source split changed, the development decision changed, a holdout file changed, a holdout file disappeared, or the lock metadata was altered.

## 4. Run locally

```bash
authorship-shift run-holdout \
  --lock holdout/v07/holdout_lock.json \
  --models "gemma3,qwen3:8b" \
  --judge-model gemma3
```

The runner uses only the locked samples and locked variants. Child experiments force their external-detector budget to zero. Runs are resumable, and `--max-runs` can cap a session.

When the locked suite is complete and includes both a baseline and a challenger, a paired confidence report is generated automatically under `holdout/v07/suite/`.

## Why this exists

A holdout stops being a holdout if pipeline choices keep changing in response to its results. The lock does not make misuse impossible, but it makes the intended protocol explicit and produces artifacts that reveal whether the original split, development decision, or validation texts changed after selection.

The intended sequence is:

```text
development corpus
    ↓
local ablations
    ↓
confidence + decision
    ↓
LOCK
    ↓
held-out local validation
    ↓
only then consider scarce external evaluation
```
