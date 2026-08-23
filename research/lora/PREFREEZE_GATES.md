# Pre-freeze excerpt gates

Annotation preparation is the last point at which raw excerpts may be rejected without changing a frozen training contract. Two checks run there in addition to source snapshot and canonical-text validation.

## 1. Duplicate-target guard

`prepare_lora_annotations.py` audits raw `target_text` before packet creation.

- Whitespace-normalized **exact duplicates** are fatal, whether they come from the same or different source document.
- High-similarity near duplicates (word 5-gram Jaccard >= 0.80) from **different source documents** are fatal. Different source documents can receive different train/dev/holdout assignments, so duplicated content would undermine source-level independence.
- High-similarity near duplicates from the **same source document** are reported as warnings, not fatal errors. All excerpts from one source receive the same split, but repeated extraction can still overweight that source or inflate passage-yield counts.

This gate complements the compiled-corpus near-duplicate audit; it runs earlier so obvious leakage or repeated extraction is caught before annotation packets are frozen.

A page-spanning PDF text box duplicated by the extractor on two pages does **not by itself** cross train/dev/holdout, because split assignment is source-level. It becomes a training-data problem when duplicated or near-duplicated raw excerpts are selected, which is why the hard gate is at the excerpt boundary.

## 2. Page-scoped source exclusions

A registry source can declare pages that are not eligible for target prose:

```json
"source_exclusions": [
  {
    "pages": [1],
    "category": "rights",
    "reason": "Third-party cover image and credit; exclude the entire page from target prose."
  }
]
```

Allowed categories are `rights` and `style`.

Examples:

- `rights`: third-party photographs, reproduced copyrighted passages, or other material whose rights do not follow the host document's public-domain status;
- `style`: comment letters, contractor-authored appendices, colophons, or other sections that are legally usable but outside the intended authorial distribution.

For PDF sources, every raw excerpt must also declare the exact canonical page(s) used:

```json
"metadata": {
  "source_pages": [4]
}
```

Annotation preparation verifies all of the following before packet creation:

1. `source_pages` is present and contains valid positive page numbers;
2. every declared page exists in the frozen canonical extraction;
3. `target_text` occurs on those declared canonical page(s), allowing whitespace reflow only;
4. the declared pages do not intersect any registry `source_exclusions` entry.

If an excluded page is referenced, preparation fails with the exclusion category and reason.

`metadata.source_pages` and the complete `metadata.source_exclusions` policy are copied into each annotation packet and frozen in the annotation manifest. Changing either after preparation invalidates the frozen contract.

## CBO 62264 example

The frozen CBO 62264 artifact contains a third-party cover image credited to Wenjie Zheng/Shutterstock.com on page 1. Its local registry record should therefore contain a page-1 `rights` exclusion before the source can be used for annotation. CBO-authored prose on later pages remains eligible after canonical derivation and normal passage-level review.
