# Locked Holdout Validation Protocol

The development suite is allowed to influence pipeline selection. The holdout set is not.

The lock step between those phases fingerprints the selected variants, split file, decision file, and exact holdout texts before holdout generation begins. v0.8 schema v3 also makes new locks relocatable: normal project paths are stored relative to the holdout package or corpus rather than bound to one machine's absolute checkout path.

## 1. Finish development first

Run the development ablations, confidence analysis, integrity audit, and decision engine before touching the holdout set.

```bash
authorship-shift decide --suite ablations/v08 --slots 3
```

This creates `decision.json`.

## 2. Lock the holdout

```bash
authorship-shift prepare-holdout \
  --corpus corpus \
  --development-suite ablations/v08 \
  --split corpus/split.json \
  --output holdout/v08 \
  --slots 3
```

The lock records:

- SHA-256 of the original development/holdout split
- SHA-256 of the development decision file
- selected variants
- corpus-relative holdout sample paths and SHA-256 hashes
- relocatable references to the corpus, development suite, split, and decision files when they share a filesystem
- a fingerprint over the complete lock metadata
- an external-detector allowance of zero

The baseline is included automatically so held-out changes can be evaluated against the same control.

Schema v3 uses `path_mode: portable_relative`. If the holdout directory and the related project files are moved together while preserving their relative layout, `check-holdout` should continue to verify the same lock fingerprint. On Windows, if referenced paths live on different drives, the lock falls back to absolute references rather than writing an invalid relative path.

Older schema-v2 locks that contain absolute paths remain readable and verifiable.

If `holdout_lock.json` already exists, preparation refuses to overwrite it. Starting a different holdout protocol requires an explicit new output directory or deliberate deletion of the old lock.

## 3. Verify before running

```bash
authorship-shift check-holdout --lock holdout/v08/holdout_lock.json
```

The check fails if the source split changed, the development decision changed, a holdout file changed, a holdout file disappeared, the execution partition changed, or the lock metadata was altered.

## 4. Run locally

```bash
authorship-shift run-holdout \
  --lock holdout/v08/holdout_lock.json \
  --models "gemma3,qwen3:8b" \
  --judge-model gemma3
```

The runner resolves the locked corpus reference from the lock package, reconstructs the execution partition from the lock immediately before use, and runs only the locked samples and locked variants. Child experiments force their external-detector budget to zero. Runs are resumable, and `--max-runs` can cap a session.

When the locked suite is complete and includes both a baseline and a challenger, a paired confidence report is generated automatically under `holdout/v08/suite/`.

## Why this exists

A holdout stops being a holdout if pipeline choices keep changing in response to its results. The lock does not make misuse impossible, but it makes the intended protocol explicit and produces artifacts that reveal whether the original split, development decision, validation texts, or execution partition changed after selection.

Making path references relocatable also separates content integrity from the accidental location of a checkout. A copied research package should not become invalid merely because its parent directory changed; its hashes should fail only when the protected artifacts or lock metadata actually change.

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
