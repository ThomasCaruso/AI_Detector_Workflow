# Business-analysis source candidates

This is a sourcing log, not an approval list. Every item remains `status: candidate` until the exact artifact is downloaded, hashed, reviewed for third-party material and authorship consistency, and shown to yield suitable sustained prose.

## Rights pools

### GAO

GAO reports include an in-document U.S. Government work notice and warn that individual products can contain copyrighted images or other separately sourced material. Review the exact report and excerpt; do not treat the agency-level rule as blanket approval of every element.

### CBO

CBO's official copyright policy states that the information and documents on its website are government works in the public domain. Exact reports still require artifact snapshotting and passage-level review for reproduced/quoted third-party material and distinct authorial voices.

Policy: https://www.cbo.gov/about/privacy

## Candidate documents

| candidate | source_id to use after selection | document | date | fit / review note |
|---|---|---|---|---|
| GAO 1 | `gao-26-108140` | *Weapon System Sustainment: DOD Identified Critical Cost Growth, and the Army Should Take Action to Yield Cost Savings* (GAO-26-108140) | 2026-04-23 | Rights basis is strong. Accessible report text contains multiple sustained narrative sections despite extensive figures/bullets. Exclude Appendix IV DOD comments as a distinct authorial voice and exclude image/table material. |
| GAO 2 | `gao-25-107604` | *2025 Annual Report: Opportunities to Reduce Fragmentation, Overlap, and Duplication and Achieve an Additional One Hundred Billion Dollars or More in Future Financial Benefits* (GAO-25-107604) | 2025-05-13 | Candidate. Explicitly reissued with revisions on 2025-05-13; `source_snapshot.revision_label` must record that state. Verify sustained prose yield before approval. |
| CBO 1 | `cbo-62265` | *Estimates of the Cost of Federal Credit Programs in 2027* | 2026-07-22 | Strong financial-analysis fit. Prose-dense treatment of credit volumes, subsidy rates, FCRA vs fair-value measurement, and program-level changes. Review tables/notes separately from prose. |
| CBO 2 | `cbo-62264` | *The Treasury's Assistance to the Airline Industry and National Security Businesses During the COVID-19 Pandemic* | 2026-06-25 | Strong business/industry-analysis fit. Examines assistance terms plus economic and budgetary effects. Check any reproduced source material and quotations before excerpting. |
| CBO 3 | `cbo-62550` | *The Navy's New Battleship Program: Costs and Implications for the Shipbuilding Industrial Base* | 2026-08-05 | Strong cost/industrial-base analysis with sustained narrative sections. Exclude figure notes and any quoted third-party material; preserve CBO-authored analysis only. |
| CBO 4 | `cbo-61945` | *Federal Excise Tax Revenues* | 2026-08-03 | Moderate financial/economic-analysis fit. Useful if excerpts emphasize analytical treatment of revenue drivers/models rather than tax-law description or table-heavy sections. |

Canonical pages:

- https://www.gao.gov/products/gao-26-108140
- https://www.gao.gov/products/gao-25-107604
- https://www.cbo.gov/publication/62265
- https://www.cbo.gov/publication/62264
- https://www.cbo.gov/publication/62550
- https://www.cbo.gov/publication/61945

## GAO-26-108140 excerpt-viability pilot

A manual pass over the accessible report text found at least six plausible sustained narrative blocks in the target 80-500-word range. Approximate block sizes were:

```text
156
313
198
198
172
202 words
```

These came from GAO-authored report/letter, methodology, cost-mitigation, and analysis/conclusion sections—not the DOD comment appendix, tables, captions, or image material.

That result is enough to keep GAO in the pool: one report can plausibly yield 3-5 clean excerpts. It is not evidence that every GAO report will. Repeat this passage-level viability check before committing each document slot.

## Approval checklist per document

Before changing any candidate to `approved`:

1. Replace any slot ID with the stable document-specific `source_id` above or another final identifier.
2. Download/freeze the exact artifact used for review.
3. Run `scripts/hash_source_artifact.py` and populate `source_snapshot`.
4. Record any published revision/reissue label.
5. Confirm the document-level rights basis.
6. Identify and exclude third-party copyrighted/reproduced material.
7. Identify and exclude distinct authorial voices even when their rights are clean.
8. Confirm roughly 3-5 usable 80-500-word prose excerpts without relying on tables, bullets, captions, or boilerplate.
9. Only then change `status` to `approved`.
