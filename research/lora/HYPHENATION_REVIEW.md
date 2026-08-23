# Evidence-assisted line-break hyphenation review

PDF extraction can insert line-break hyphens into ordinary words while genuine hyphenated compounds and alphanumeric designators also exist. Canonical extraction therefore does not guess whether a break should be joined or kept.

Use the same-document review helper after the current non-hyphen correction ledger has been applied:

```bash
python scripts/review_linebreak_hyphenation.py \
  research/lora/local_corpus/extracted/cbo-62550.canonical.json \
  --json-out research/lora/local_corpus/extracted/cbo-62550.hyphenation-review.json
```

For long documents, restrict emitted suggestions to candidate target pages while retaining full-document evidence:

```bash
python scripts/review_linebreak_hyphenation.py \
  research/lora/local_corpus/extracted/gao-25-107604.base.json \
  --pages "8-15,22,31-35" \
  --json-out research/lora/local_corpus/extracted/gao-25-107604.hyphenation-review.json
```

The report is advisory only. It does not modify canonical text or write the correction ledger.

The detector covers alphabetic and alphanumeric token fragments, including internal slashes. That matters for real extraction failures such as `COVID-\n19`, `DDG-\n51`, and `F/A-\n18`. Broader detection deliberately also surfaces ambiguous cases such as a word interrupted by a numeric footnote marker (`accept-\n32`). Coverage is not confidence: those cases remain unresolved unless same-document evidence or human inspection establishes the correct repair.

For each detected candidate it checks the whole document, case-insensitively and with alphanumeric boundaries, for the closed form and the inline hyphenated form:

- `JOIN`: closed form appears elsewhere and hyphenated form does not. Proposed repair removes both the line break and hyphen.
- `KEEP`: hyphenated form appears elsewhere and closed form does not. Proposed repair removes only the line break.
- `CONFLICT`: both forms appear elsewhere. Human review is mandatory and no repair is proposed.
- `UNRESOLVED`: neither form appears elsewhere. Human review is mandatory and no repair is proposed.

Examples:

- `charac-\nteristics` with `characteristics` elsewhere -> `JOIN`.
- `COVID-\n19` with `COVID-19` elsewhere -> `KEEP`.
- `DDG-\n51` with `DDG-51` elsewhere -> `KEEP`.
- `accept-\n32` with neither `accept32` nor `accept-32` elsewhere -> `UNRESOLVED`; inspect the page because the number may be a footnote interruption rather than part of the word.

Even `JOIN` and `KEEP` are suggestions, not automatic corrections. A reviewer must inspect the source page and explicitly copy the accepted repair into the page-scoped correction ledger with `expected_count`. The existing ledger checks then bind that decision to the exact artifact SHA-256 and base extraction SHA-256.

Do not use an external dictionary, spellchecker, language model, or general de-hyphenation regex as an automatic authority in the first corpus. Same-document evidence is useful for triage; the reviewed correction ledger remains the only mechanism allowed to change canonical text.
