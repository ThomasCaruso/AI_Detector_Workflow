# Reproducibility, Confidence, and Integrity

v0.5 adds two controls that are easy to skip in adversarial-classifier research: uncertainty estimates and tamper-evident experiment records.

## Paired confidence analysis

Ablation variants are evaluated on the same development samples. `confidence` therefore treats each sample as a pair rather than comparing unrelated aggregate means.

```bash
authorship-shift confidence --suite ablations/v05 --baseline baseline
```

For each challenger and local metric, the report includes:

- paired sample count
- baseline and challenger means
- raw mean delta
- an oriented improvement where positive always means better
- deterministic bootstrap confidence interval for the paired mean improvement
- challenger win rate
- tie rate
- exact two-sided sign-test p-value

The default is a 95% bootstrap interval with 2,000 resamples. The bootstrap PRNG is seeded so rerunning the same suite produces the same report.

These statistics summarize local fidelity, quality, structure, diversity, and compute diagnostics. They do **not** estimate a proprietary detector score.

## Content-addressed experiments

New experiments record SHA-256 hashes for the source and canonicalized configuration. Every candidate stores a hash of its exact text. Freezing a candidate records and verifies another hash for the immutable text file.

Before an external result can be recorded, the repository verifies that the frozen file still matches the candidate. The external-result JSON stores the candidate SHA-256 so a later audit can prove which exact text was evaluated.

## Integrity audit

Audit one experiment:

```bash
authorship-shift audit --target experiments/product_distribution
```

Audit a complete ablation suite:

```bash
authorship-shift audit --target ablations/v05 --suite
```

The audit checks:

- source/config hashes when available
- candidate-file presence and content hashes
- frozen-file identity
- frozen metadata hashes
- external-result candidate references
- external query count versus result files
- zero external detector results inside ablation runs

Legacy experiments created before v0.5 can still be audited. Missing historical hashes are reported as warnings rather than invented after the fact.

## Recommended promotion rule

Do not promote a local pipeline merely because its aggregate mean is higher. Prefer variants that:

1. pass the hard fidelity and quality gates,
2. show positive paired changes across multiple development samples,
3. have confidence intervals that are not dominated by a few outliers,
4. pass the integrity audit,
5. remain strong on held-out samples before any scarce external evaluation.
