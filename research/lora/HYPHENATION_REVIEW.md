# Evidence-assisted line-break hyphenation review

PDF extraction can insert line-break hyphens into ordinary words while genuine hyphenated compounds also exist. Canonical extraction therefore does not guess whether a break should be joined or kept.

Use the same-document review helper after the current non-hyphen correction ledger has been applied:

```bash
python scripts/review_linebreak_hyphenation.py \
  research/lora/local_corpus/extracted/cbo-62550.canonical.json \
  --json-out research/lora/local_corpus/extracted/cbo-62550.hyphenation-review.json
```

The report is advisory only. It does not modify canonical text or write the correction ledger.

For each `word-\nbreak` candidate it checks the whole document, case-insensitively and with word boundaries, for the closed form (`wordbreak`) and the inline hyphenated form (`word-break`):

- `JOIN`: closed form appears elsewhere and hyphenated form does not. Proposed repair removes both the line break and hyphen.
- `KEEP`: hyphenated form appears elsewhere and closed form does not. Proposed repair removes only the line break.
- `CONFLICT`: both forms appear elsewhere. Human review is mandatory and no repair is proposed.
- `UNRESOLVED`: neither form appears elsewhere. Human review is mandatory and no repair is proposed.

Even `JOIN` and `KEEP` are suggestions, not automatic corrections. A reviewer must inspect the source page and explicitly copy the accepted repair into the page-scoped correction ledger with `expected_count`. The existing ledger checks then bind that decision to the exact artifact SHA-256 and base extraction SHA-256.

Do not use an external dictionary, spellchecker, language model, or general de-hyphenation regex as an automatic authority in the first corpus. Same-document evidence is useful for triage; the reviewed correction ledger remains the only mechanism allowed to change canonical text.
