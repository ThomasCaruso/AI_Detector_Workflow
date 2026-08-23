# Business-analysis corpus pilot findings

This note records measured local-artifact results from the first five business-analysis sources: four CBO reports and one GAO report. It is an empirical sourcing record, not a substitute for the local registry, artifact hashes, correction ledgers, or frozen annotation manifests.

## Five-document result

| source | pages used | heuristic clean passages | segmentation-independent prose words | reviewed ledger rules |
|---|---:|---:|---:|---:|
| `cbo-62264` | 25; page 1 excluded for rights | 23 | 7,652 | 151 |
| `cbo-62265` | 15 | 13 | 5,413 | 103 |
| `cbo-62550` | 12 | 15 | 4,775 | 76 |
| `cbo-61945` | 13 | 14 | 5,135 | 74 |
| `gao-26-108140` | 56; pages 55-56 excluded for style | 14 | 6,681 | 1 |

Combined: 79 heuristic passages and 29,656 prose words from five independent documents across two publishers/agencies.

Passage counts are useful for sourcing but are not stable enough to be a corpus contract. They moved when line-break repairs changed line lengths and exposed weaknesses in heuristic paragraph segmentation. Segmentation-independent prose-word volume is the more stable volume measure.

The GAO source is an important cost and diversity result. It contributes prose volume comparable to the CBO reports while requiring dramatically fewer reviewed extraction repairs. That makes GAO worth retaining as an independent source pool rather than filling all six business-analysis slots from one publisher.

## Corpus constraint decision

For the first adapter pilot:

- **Hard structural floor:** at least 6 independent approved documents per genre.
- **Monitoring threshold:** at least 25 clean passages per genre.

The earlier 25-passage number is no longer treated as a binding target. Four CBO documents already exceeded it substantially, and the fifth GAO source reinforces that result. It remains useful as a low-volume warning, while document independence remains the binding design constraint because additional passages from one source cannot replace held-out source diversity.

Do not generalize this yield to every genre. Continue reporting clean passage count and prose-word volume for each source pool so the monitoring threshold can be revisited if another genre behaves differently.

## Extraction findings that changed the workflow

### Manual split-capital review remains mandatory

Single-capital-plus-space patterns are not safely auto-repairable. Real examples include ordinary articles (`A common method`), labels (`Part B account`, `B minus`), and genuine extraction artifacts (`T reasury`). GAO-26-108140 produced no genuine split-capital artifacts in the selected pages despite many superficially similar hits, showing that heuristic precision is publisher/typesetting-dependent. Every candidate repair requires local context.

### Hyphenation remains reviewed, not guessed

Same-document evidence can resolve many line-break hyphens, but unresolved cases include closed words, genuine compounds, URLs, designators, and text interrupted by footnote numbers. The advisory reviewer now detects alphanumeric cases such as `COVID-\n19`, `DDG-\n51`, and `F/A-\n18`; broader detection intentionally leaves ambiguous cases such as `accept-\n32` unresolved for human inspection. Only the reviewed correction ledger changes canonical text.

### Correction rules must not overlap or depend on order

A short rule such as `T ransport` can match inside `T ransportation`. Canonical extraction therefore validates every reviewed rule against the original page text, applies accepted rules simultaneously, and rejects overlapping source spans. This makes correction application invariant to ledger ordering and prevents one replacement from creating text that a later replacement silently rewrites.

`corrections_sha256` likewise fingerprints correction semantics independent of replacement-list ordering. Reordering an otherwise identical ledger must not create a different derivation identity.

### PDF extraction can duplicate page-spanning text

A page-spanning text box can be emitted in full on multiple pages. Exact duplicate target excerpts are blocked before annotation freeze. High-similarity duplicates across different source documents are also blocked; same-source near-duplicates are surfaced for overweighting review.

### Rights and authorship exclusions must be machine-enforceable

`cbo-62264` contains a third-party Shutterstock cover image on page 1. The registry records that page as a rights exclusion. `gao-26-108140` contains DOD-authored correspondence in Appendix IV on PDF pages 55-56; those pages are recorded as a style/authorship exclusion even though the scanned letter currently has no extractable text. PDF excerpts declare `metadata.source_pages`, and annotation preparation rejects excerpts that overlap either exclusion type.

## Selective correction for long documents

Do **not** make every page of a long PDF typographically perfect before deciding whether the document is useful.

GAO-26-108140 validates the selective-review workflow: a 58-page artifact reached a frozen usable state with one reviewed ledger rule, versus dozens to hundreds of rules for much shorter CBO reports.

For long sources such as the remaining GAO report:

1. hash and base-extract the entire frozen artifact;
2. review rights/authorship structure and identify candidate prose pages;
3. choose the passages that may enter the corpus;
4. fully correct extraction artifacts on those target-bearing pages;
5. regenerate the canonical extraction and freeze its derivation;
6. create raw excerpts only from corrected, page-bound canonical text;
7. before annotation freeze, finish any additional corrections required by every selected excerpt.

Unused pages may retain extraction artifacts. That is acceptable because they cannot enter `target_text` without first being corrected and causing a new canonical-text hash. Once annotation packets are frozen, changing the correction ledger is a new source-target contract and must not be done silently.

## Remaining business-analysis requirement

The pool currently has five frozen independent documents. The genre is not structurally complete until a sixth independent approved document is frozen. `gao-25-107604` is the next candidate; its 154-page length should be handled with the same selective-page workflow rather than whole-document cleanup.
