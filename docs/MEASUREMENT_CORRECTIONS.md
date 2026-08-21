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

## 2026-08-21 — immutable precheck: integer percentages written as words

### Trigger

The corrected-template `science_summary_001` 5-profile x 4-sample batch produced 20 completed generations. Ten candidates failed exactly one immutable, `8%`, because they rendered the value as `8 percent` or `eight percent`. All other checkable details (`1,240`, `150`, and `30`) were preserved, word counts were in range, and the batch contained no near-duplicate candidates.

This is the same class of instrument error as the earlier bare-integer correction: the value and unit are unchanged, but the precheck required one surface spelling. The generated outputs predate this correction, so re-analysis does not alter the generation process.

### Correction

A deliberately narrow percentage-equivalence rule was added:

- an **unsigned integer percentage from 0 through 99** written as `N%` may match `N percent`, the equivalent number word plus `percent`, or the equivalent number word plus `per cent`;
- the rule does **not** normalize decimals, currency, units, multipliers, or other percent-like language;
- `8%` does not match `18 percent`, `80 percent`, `8.5 percent`, `8 percentage points`, or `eight percentage points`;
- percentage points remain distinct because an 8% relative change and an 8-percentage-point change are not generally equivalent.

Regression tests pin both the accepted equivalents and the non-equivalent boundary cases.

### What this correction is allowed to change

- immutable coverage for integer percentages;
- candidate eligibility when the only prior failure was percentage surface form;
- gate pass/fail status.

### What this correction must not change

- any generated candidate text;
- within-profile dispersion;
- between-profile dispersion;
- collapse ratio;
- permutation p-value;
- profile labels;
- generation prompts or sampling behavior;
- external detector observations.

### Experimental policy

Do not regenerate Science because of this correction. Re-run deterministic analysis on the frozen 20 outputs. The Science collapse ratio must remain `1.227` and its permutation p-value must remain `0.0010`; if either changes, treat that as a bug. The prior gate failure remains part of the experimental history and should be documented as a precheck false positive rather than overwritten conceptually.
