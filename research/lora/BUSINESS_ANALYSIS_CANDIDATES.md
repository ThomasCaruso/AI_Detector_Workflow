# Business-analysis source candidates

This is a sourcing log, not an approval list. Every item remains `status: candidate` until the exact artifact is downloaded, hashed, reviewed for third-party material and authorship consistency, and shown to yield suitable sustained prose.

## Rights pools

### GAO

GAO reports include an in-document U.S. Government work notice and warn that individual products can contain copyrighted images or other separately sourced material. Review the exact report and excerpt; do not treat the agency-level rule as blanket approval of every element.

### CBO

CBO's official copyright policy states that the information and documents on its website are government works in the public domain. Exact reports still require artifact snapshotting and passage-level review for reproduced/quoted third-party material and distinct authorial voices.

Policy: https://www.cbo.gov/about/privacy

### Verification provenance for the CBO pool

The CBO rights-policy, title/date, report-home-page, and View Document relationships recorded below were verified through the web research surface used during this project. The local verification environment separately corroborated several report-home-page search results but could not fetch `cbo.gov` directly because that environment received HTTP 403 responses.

Treat this sourcing log as research evidence, not as approval. The final registry still requires a locally downloaded artifact, exact observed artifact locator, SHA-256, passage-level authorship review, and document-level rights review before `status` may become `approved`.

## CBO identifier convention

CBO can expose more than one numeric `/publication/` identifier for the same report. For the reports checked here, one node is the report **home page** and another is the separate HTML **View Document** page.

For this corpus:

- `source_id` uses the report home-page ID;
- `canonical_url` uses the report home page;
- `document_locator` records the **observed** View Document ID and/or the exact observed artifact URL/filename;
- `source_snapshot.sha256` pins the actual downloaded artifact bytes.

**Never construct or infer a PDF/artifact URL from a publication number.** A filename pattern may happen to match a report-home-page ID, but that is not part of the corpus contract. Record the artifact URL or local artifact locator actually observed during download/review.

Do not replace a home-page source ID with a View Document node ID merely because the latter contains the full HTML text.

Verified examples:

| report | home page / source ID | View Document HTML | observed downloadable PDF filename |
|---|---|---|---|
| *Estimates of the Cost of Federal Credit Programs in 2027* | `62265` | `62594` | `62265-federal-credit-programs.pdf` |
| *The Navy's New Battleship Program: Costs and Implications for the Shipbuilding Industrial Base* | `62550` | `62644` | `62550-battleships.pdf` |
| *Estimates of the Cost of Federal Credit Programs in 2025* | `60517` | `60682` | `60517-federal-credit-programs.pdf` |

The 2025 example is useful because search results can make the View Document node (`60682`) look like the report identifier. The report home page is `60517`; `60682` is the HTML document node. That reinforces the rule to distinguish node types rather than deriving identity from whichever numeric URL appears first.

The battleship home page also states that CBO reposted the report with a correction on August 7, 2026. A downloaded post-correction artifact should record that fact in `source_snapshot.revision_label`; the SHA-256 remains the authoritative byte-level identity.

## Candidate documents

| candidate | source_id to use after selection | document | date | fit / review note |
|---|---|---|---|---|
| GAO 1 | `gao-26-108140` | *Weapon System Sustainment: DOD Identified Critical Cost Growth, and the Army Should Take Action to Yield Cost Savings* (GAO-26-108140) | 2026-04-23 | Rights basis is strong. Exclude Appendix IV DOD comments as a distinct authorial voice and exclude image/table material. **Passage yield remains unverified against the frozen artifact.** Earlier web-derived block counts were based on truncated text and are discarded. |
| GAO 2 | `gao-25-107604` | *2025 Annual Report: Opportunities to Reduce Fragmentation, Overlap, and Duplication and Achieve an Additional One Hundred Billion Dollars or More in Future Financial Benefits* (GAO-25-107604) | 2025-05-13 | Candidate. Explicitly reissued with revisions on 2025-05-13; `source_snapshot.revision_label` must record that state. Frozen-artifact passage yield remains to be measured. |
| CBO 1 | `cbo-62265` | *Estimates of the Cost of Federal Credit Programs in 2027* | 2026-07-22 | **Frozen artifact screened locally.** SHA-256 `f712bdb6e2721947eb5ac0bc6e1da4534446305e0da350349e1cac9317bd21d9`; 355,376 bytes; 15 pages; embedded author/title/date match. At least 11 clean sustained CBO-authored passages measured in the 80-500-word range. No publication revision notice found; `revision_label` should be null for this artifact. Formal rights approval still required. |
| CBO 2 | `cbo-62264` | *The Treasury's Assistance to the Airline Industry and National Security Businesses During the COVID-19 Pandemic* | 2026-06-25 | Strong business/industry-analysis fit. Examines assistance terms plus economic and budgetary effects. The observed artifact contains a third-party Shutterstock cover image, which must not enter target prose. Check any other reproduced source material and quotations before excerpting. |
| CBO 3 | `cbo-62550` | *The Navy's New Battleship Program: Costs and Implications for the Shipbuilding Industrial Base* | 2026-08-05 | Strong cost/industrial-base analysis. Home page is `/publication/62550`; full HTML View Document node is `/publication/62644`; observed PDF filename is `62550-battleships.pdf`. CBO reports a corrected repost on 2026-08-07, so snapshot the corrected artifact deliberately. |
| CBO 4 | `cbo-61945` | *Federal Excise Tax Revenues* | 2026-08-03 | Moderate financial/economic-analysis fit. CBO home page `/publication/61945` is verified. Useful if excerpts emphasize analytical treatment of revenue drivers/models rather than tax-law description or table-heavy sections. |

Canonical report home pages:

- https://www.gao.gov/products/gao-26-108140
- https://www.gao.gov/products/gao-25-107604
- https://www.cbo.gov/publication/62265
- https://www.cbo.gov/publication/62264
- https://www.cbo.gov/publication/62550
- https://www.cbo.gov/publication/61945

## Frozen-source audit: CBO-62265

Artifact screened locally against the same bytes used for hashing:

```text
filename: 62265-federal-credit-programs.pdf
sha256: f712bdb6e2721947eb5ac0bc6e1da4534446305e0da350349e1cac9317bd21d9
size: 355,376 bytes
pages: 15
embedded author: Congressional Budget Office
embedded title: Estimates of the Cost of Federal Credit Programs in 2027
embedded creation date: 2026-07-22
revision notice: none found
```

Measured clean passage inventory found at least 11 sustained CBO-authored blocks in
the target 80-500-word range, including blocks on pages 1, 2, 3, 4, 6, 7, 10, and
14. Measured lengths ranged from 122 to 457 words. This count is a floor rather
than an exhaustive enumeration.

Rights/style exclusions from the frozen artifact:

- exclude Table 1 (page 5) and Figure 1 (page 9), including notes;
- exclude the page-15 director signature graphic and colophon/about-this-document material;
- exclude numbered footnotes as a citation-dense register distinct from target prose;
- exclude bulleted lists and the page-1 methodological `Notes:` block;
- exclude running headers.

No comment letters, contractor appendices, or reproduced third-party prose were
identified in the screened artifact. No third-party image credit was identified in
this PDF; the page-15 graphic credit is CBO-produced.

**Viability verdict:** strong candidate / approve subject to formal rights sign-off.
The artifact demonstrates that passage yield can materially exceed the earlier
3-5-per-document planning assumption.

## Extraction finding from CBO-62265

The frozen PDF also established that raw PDF extraction is not itself canonical
training text. The local pypdf extraction contained systematic artifacts including
intra-word spacing, visual-line hyphenation, and presentation ligatures. Those
cannot be repaired by an undocumented manual cleanup step because two extractors or
two cleanup conventions could derive different targets from the same PDF hash.

The corpus pipeline therefore freezes a separate text-derivation contract:

```text
frozen PDF bytes
-> pinned pypdf version/mode
-> deterministic safe normalization
-> reviewed page-scoped correction ledger
-> canonical-text SHA-256
-> whitespace-only target excerpt selection
```

See `CORPUS_PIPELINE.md` and `scripts/extract_source_text.py`.

## Corpus constraints after first frozen audit

Use two intentionally asymmetric constraints per genre:

- **hard structural floor:** at least 6 independent approved documents;
- **provisional volume target:** at least 25 clean passages.

The first protects split independence and cannot be replaced by more excerpts from
a high-yield source. The second is an empirical starting point. CBO-62265 alone
contributes at least 11 viable passages, so passage volume may be easier to satisfy
than document independence in the business-analysis genre; do not generalize that
yield to other source pools or genres without frozen-artifact audits.

## Approval checklist per document

Before changing any candidate to `approved`:

1. Replace any slot ID with the stable document-specific `source_id` above or another final identifier.
2. Confirm that `source_id` and `canonical_url` identify the same report home page, not a View Document node or other related object.
3. Download/freeze the exact artifact used for review; do not derive the artifact URL from an identifier convention.
4. Record the exact observed artifact URL/filename or stable local locator in `document_locator`.
5. Run `scripts/hash_source_artifact.py` and populate `source_snapshot`.
6. Record any published revision/reissue/correction label.
7. Confirm the document-level rights basis.
8. Identify and exclude third-party copyrighted/reproduced material.
9. Identify and exclude distinct authorial voices even when their rights are clean.
10. For PDFs, create and freeze the canonical text derivation; record all ambiguous extraction repairs in the reviewed correction ledger.
11. Measure clean 80-500-word passage yield against the frozen artifact/canonical text rather than web-rendered snippets.
12. Only then change `status` to `approved`.
