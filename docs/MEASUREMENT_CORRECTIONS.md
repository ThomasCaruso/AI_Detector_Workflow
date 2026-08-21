# Measurement corrections

This file records deterministic measurement corrections discovered after generation data existed. The purpose is to distinguish a justified instrument repair from changing an experiment until its conclusion improves.

## 2026-08-21 — immutable precheck: number words and sentence-initial terminology

### Trigger

The corrected-template `business_valuation_001` 5-profile x 4-sample batch produced 20 completed generations. Three mechanism-first candidates failed the immutable-detail precheck even though manual inspection showed that the underlying facts were preserved:

- two candidates rendered the bare integer `9` as `nine` in the phrase describing approximately nine percentage points of growth;
- one candidate rendered the concept `Normalized EBITDA` without preserving that exact sentence-initial capitalization/phrase surface form.

The second failure mode had been identified earlier as a residual risk in the capitalization heuristic. The source itself contains both `Normalized EBITDA` and later `normalized EBITDA`, which supplies independent evidence that the phrase is ordinary terminology rather than a proper name.

### Correction

Two deliberately narrow rules were added to `candidate_lab.py`:

1. A **bare unsigned integer from 0 through 99** may match its ordinary spelled-out equivalent. This applies only to bare integers. Currency, percentages, decimals, units, multipliers, and punctuated values remain exact-surface checks. Compound values accept either a hyphen or a space (`twenty-one` / `twenty one`). Boundaries prevent `9` from matching `nineteen`, `nine-year`, `9.1x`, `1,900`, or `2029`.
2. A **multiword capitalized phrase is not extracted as a name when the same words occur elsewhere in the source with different casing**, unless every token is all caps. This retains proper-name evidence such as `Northstar Mobility` while excluding sentence-initial common-noun terminology such as `Normalized EBITDA` when the source later uses `normalized EBITDA`.

Regression tests cover both rules and preserve the existing longer-number boundary cases.

### What this correction is allowed to change

- immutable-detail extraction;
- immutable coverage;
- gate pass/fail status;
- fidelity-evidence reporting if the extracted item set changes.

### What this correction must not change

- any generated candidate text;
- within-profile dispersion;
- between-profile dispersion;
- collapse ratio;
- permutation p-value;
- profile labels;
- generation prompts or sampling behavior;
- external detector observations.

The business batch should therefore be re-analyzed from the frozen 20 outputs. If its gate status changes, the old gate result remains part of the experimental history; the collapse statistic itself should be identical.

### Experimental policy

Do not regenerate the business candidates because of this correction. Re-run only deterministic analysis. If the collapse statistic changes, treat that as a bug because this measurement repair has no path to alter the texts or profile assignments.
