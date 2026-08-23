# Business-analysis corpus pilot findings

This note records measured local-artifact results from the first four CBO sources. It is an empirical sourcing record, not a substitute for the local registry, artifact hashes, correction ledgers, or frozen annotation manifests.

## Four-document CBO result

| source | pages used | heuristic clean passages | segmentation-independent prose words | remaining line-break hyphen artifacts |
|---|---:|---:|---:|---:|
| `cbo-62264` | 25; page 1 excluded for rights | 23 | 7,652 | 0 |
| `cbo-62265` | 15 | 13 | 5,413 | 0 |
| `cbo-62550` | 12 | 15 | 4,775 | 0 |
| `cbo-61945` | 13 | 14 | 5,135 | 0 |

Combined: 65 heuristic passages and 22,975 prose words from four independent documents.

Passage counts are useful for sourcing but are not stable enough to be a corpus contract. They moved when line-break repairs changed line lengths and exposed weaknesses in heuristic paragraph segmentation. Segmentation-independent prose-word volume is the more stable volume measure.

## Corpus constraint decision

For the first adapter pilot:

- **Hard structural floor:** at least 6 independent approved documents per genre.
- **Monitoring threshold:** at least 25 clean passages per genre.

The earlier 25-passage number is no longer treated as a binding target. Four CBO documents already exceed it substantially. It remains useful as a low-volume warning, while document independence remains the binding design constraint because additional passages from one source cannot replace held-out source diversity.

Do not generalize CBO yield to every genre. Continue reporting clean passage count and prose-word volume for each source pool so the monitoring threshold can be revisited if another genre behaves differently.

## Extraction findings that changed the workflow

### Manual split-capital review remains mandatory

Single-capital-plus-space patterns are not safely auto-repairable. Real examples include ordinary articles (`A common method`), labels (`Part B account`, `B minus`), and genuine extraction artifacts (`T reasury`). Every candidate repair requires local context.

### Hyphenation remains reviewed, not guessed

Same-document evidence can resolve many line-break hyphens, but unresolved cases include both closed words and genuine compounds. The advisory hyphenation tool may propose `JOIN` or `KEEP`; only the reviewed correction ledger changes canonical text.

### Correction rules must not overlap

A short rule such as `T ransport` can match inside `T ransportation`. Canonical extraction therefore applies reviewed rules simultaneously against the original page text and rejects overlapping source spans. This makes correction application invariant to ledger ordering.

### PDF extraction can duplicate page-spanning text

A page-spanning text box can be emitted in full on multiple pages. Exact duplicate target excerpts are blocked before annotation freeze. High-similarity duplicates across different source documents are also blocked; same-source near-duplicates are surfaced for overweighting review.

### Rights exclusions must be machine-enforceable

`cbo-62264` contains a third-party Shutterstock cover image on page 1. The registry records that page as a rights exclusion, PDF excerpts declare `metadata.source_pages`, and annotation preparation rejects excerpts that overlap excluded pages. The exclusion removed no usable prose passage and only a small amount of cover text from the measured prose volume.

## Selective correction for long documents

Do **not** make every page of a long PDF typographically perfect before deciding whether the document is useful.

For long sources such as the GAO reports:

1. hash and base-extract the entire frozen artifact;
2. review rights/authorship structure and identify candidate prose pages;
3. choose the passages that may enter the corpus;
4. fully correct extraction artifacts on those target-bearing pages;
5. regenerate the canonical extraction and freeze its derivation;
6. create raw excerpts only from corrected, page-bound canonical text;
7. before annotation freeze, finish any additional corrections required by every selected excerpt.

Unused pages may retain extraction artifacts. That is acceptable because they cannot enter `target_text` without first being corrected and causing a new canonical-text hash. Once annotation packets are frozen, changing the correction ledger is a new source-target contract and must not be done silently.
