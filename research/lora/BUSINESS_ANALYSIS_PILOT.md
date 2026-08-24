# Business-analysis corpus pilot findings

This note records measured local-artifact results from the first six business-analysis sources: four CBO reports and two GAO reports. It is an empirical sourcing record, not a substitute for the local registry, artifact hashes, correction ledgers, or frozen annotation manifests.

## Six-document result

| source | pages used | heuristic clean passages | segmentation-independent prose words | reviewed ledger rules |
|---|---:|---:|---:|---:|
| `cbo-62264` | 25; page 1 excluded for rights | 23 | 7,652 | 151 |
| `cbo-62265` | 15 | 13 | 5,413 | 103 |
| `cbo-62550` | 12 | 15 | 4,775 | 76 |
| `cbo-61945` | 13 | 14 | 5,135 | 74 |
| `gao-26-108140` | 56; pages 55-56 excluded for style | 14 | 6,681 | 1 |
| `gao-25-107604` | selected pages 7-42 | 8 | 4,970 | 7 |

Combined: **87 heuristic passages and 34,626 prose words from six independent documents across two publishers/agencies.** All six frozen artifacts have canonical text derivations; the local registry remains the authority for whether each source has been promoted from `candidate` to `approved`.

Passage counts are useful for sourcing but are not stable enough to be a corpus contract. They moved when line-break repairs changed line lengths and exposed weaknesses in heuristic paragraph segmentation. Segmentation-independent prose-word volume is the more stable volume measure.

The GAO sources are important cost and diversity results. Together they contribute substantial prose volume while requiring dramatically fewer reviewed extraction repairs than the CBO reports. They also add a second agency/typesetting profile rather than filling all six business-analysis slots from one publisher.

## Corpus constraint decision

For the first adapter pilot:

- **Hard structural floor:** at least 6 independent approved documents per genre.
- **Monitoring threshold:** at least 25 clean passages per genre.

The earlier 25-passage number is no longer treated as a binding target. The six frozen business-analysis sources exceed it by more than 3x. It remains useful as a low-volume warning, while document independence remains the binding design constraint because additional passages from one source cannot replace held-out source diversity.

Do not generalize this yield to every genre. Continue reporting clean passage count and prose-word volume for each source pool so the monitoring threshold can be revisited if another genre behaves differently.

## Extraction findings that changed the workflow

### Manual split-capital review remains mandatory

Single-capital-plus-space patterns are not safely auto-repairable. Real examples include ordinary articles (`A common method`), labels (`Part B account`, `B minus`), and genuine extraction artifacts (`T reasury`). The two GAO reports produced essentially no genuine split-capital artifacts on selected target pages despite many superficially similar hits, showing that heuristic precision is publisher/typesetting-dependent. Every candidate repair requires local context.

### Hyphenation remains reviewed, not guessed

Same-document evidence can resolve many line-break hyphens, but unresolved cases include closed words, genuine compounds, URLs, designators, statutes, and text interrupted by footnote numbers. The advisory reviewer detects alphanumeric cases such as `COVID-\n19`, `DDG-\n51`, and `F/A-\n18`; broader detection intentionally leaves ambiguous cases such as `accept-\n32` unresolved for human inspection. Only the reviewed correction ledger changes canonical text.

`gao-25-107604` reinforces the rule: all seven selected-page repairs were `KEEP`, including report/statute identifiers that required human review because no supporting inline form existed. No blanket `JOIN` fallback would have been safe.

### Correction rules must not overlap or depend on order

A short rule such as `T ransport` can match inside `T ransportation`. Canonical extraction therefore validates every reviewed rule against the original page text, applies accepted rules simultaneously, and rejects overlapping source spans. This makes correction application invariant to ledger ordering and prevents one replacement from creating text that a later replacement silently rewrites.

`corrections_sha256` likewise fingerprints correction semantics independent of replacement-list ordering. Reordering an otherwise identical ledger must not create a different derivation identity.

### PDF extraction can duplicate page-spanning text

A page-spanning text box can be emitted in full on multiple pages. Exact duplicate target excerpts are blocked before annotation freeze. High-similarity duplicates across different source documents are also blocked; same-source near-duplicates are surfaced for overweighting review.

### Rights and authorship exclusions must be machine-enforceable

`cbo-62264` contains a third-party Shutterstock cover image on page 1. The registry records that page as a rights exclusion. `gao-26-108140` contains DOD-authored correspondence in Appendix IV on PDF pages 55-56; those pages are recorded as a style/authorship exclusion even though the scanned letter currently has no extractable text. PDF excerpts declare `metadata.source_pages`, and annotation preparation rejects excerpts that overlap either exclusion type.

`gao-25-107604` did not require a source exclusion: the reviewed selected pages are GAO-authored, and no distinct transmitted-correspondence section or sustained third-party quoted prose was identified in the screened structure. Do not invent exclusions merely to make source records look symmetrical.

## Selective correction for long documents

Do **not** make every page of a long PDF typographically perfect before deciding whether the document is useful.

Both GAO reports validate the selective-review workflow. `gao-26-108140` froze with one reviewed ledger rule across a 58-page artifact; `gao-25-107604` froze with seven reviewed rules across a 154-page artifact while only selected target-bearing pages were corrected. A known extraction artifact outside the selected target pages was documented and correctly left untouched.

For long sources:

1. hash and base-extract the entire frozen artifact;
2. review rights/authorship structure and identify candidate prose pages;
3. choose the passages that may enter the corpus;
4. fully correct extraction artifacts on those target-bearing pages;
5. regenerate the canonical extraction and freeze its derivation;
6. create raw excerpts only from corrected, page-bound canonical text;
7. before annotation freeze, finish any additional corrections required by every selected excerpt.

Unused pages may retain extraction artifacts. That is acceptable because they cannot enter `target_text` without first being corrected and causing a new canonical-text hash. Once annotation packets are frozen, changing the correction ledger is a new source-target contract and must not be done silently.

## Business-analysis sourcing status

The frozen source pool now contains **six independent derivation-complete documents**, satisfying the pilot's source-count floor at the sourcing layer. The local registry should promote a source to `approved` only after its document-local rights/provenance, exclusions, snapshot, derivation, and viability checks are all complete.

Once all six are promoted, business analysis is source-complete for the first pilot. Do not add more business-analysis documents merely to increase volume before the other four genres reach the same six-source floor. The next sourcing priority is `technical_explanation`.
