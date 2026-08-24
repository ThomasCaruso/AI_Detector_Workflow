# Technical-explanation source candidates

This is a sourcing log, not an approval list. The target register is explanatory prose whose job is to make a mechanism intelligible: how something works, why it behaves that way, and how parts or causes connect. Prefer causal/mechanical chains and a teaching stance; reject recommendation-heavy business-analysis prose, pure procedures, standards language, tables, captions, and reference material.

The initial pool deliberately uses three publisher families, two sources each, to avoid recreating the CBO/GAO institutional-register concentration seen in `business_analysis`.

## Independence rule

Do not manufacture source independence by treating multiple chapters from one handbook as separate documents. One FAA candidate below is an independently published chapter PDF from the Powerplant handbook. If that chapter is used, **do not use another chapter from FAA-H-8083-32B as another source in this six-document pilot**.

## Candidate pool

| source_id | family | document | canonical page | observed artifact locator | initial register/risk note |
|---|---|---|---|---|---|
| `faa-phak-8083-25c` | FAA | *Pilot's Handbook of Aeronautical Knowledge*, FAA-H-8083-25C | `https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/phak` | `https://www.faa.gov/regulations_policies/handbooks_manuals/aviation/faa-h-8083-25c.pdf` | Strong explanatory material in principles of flight, aerodynamics, aircraft systems, instruments, and weather theory. Heavily illustrated; audit every selected page for third-party figures/credits and reject procedural/regulatory passages. |
| `faa-amt-8083-32b-ch1` | FAA | *FAA-H-8083-32B, Chapter 1: Aircraft Engines* | `https://www.faa.gov/regulationspolicies/handbooksmanuals/aviation/faa-h-8083-32b-chapter-1-aircraft-engines` | `https://www.faa.gov/sites/faa.gov/files/03_amtp_ch1.pdf` | Mechanism-rich engine explanation and distinct from the pilot handbook. Treat this official standalone chapter PDF as one source; do not count another chapter from the same handbook as independent. Manufacturer imagery/diagrams are a likely page-level rights-review cost. |
| `nasa-sp-367` | NASA | *Introduction to the Aerodynamics of Flight*, NASA-SP-367 | `https://ntrs.nasa.gov/citations/19760003955` | `https://ntrs.nasa.gov/archive/nasa/casi.ntrs.nasa.gov/19760003955.pdf` | Excellent fit: NASA Langley author; atmosphere, fluid flow, subsonic/transonic/supersonic effects, performance, stability and control. NTRS marks it `Work of the US Gov. Public Use Permitted.` Older source; perform holdout memorization spot-check if assigned dev/holdout. |
| `nasa-tm-x-52389` | NASA | *Exploring in Aerospace Rocketry. 2 — Propulsion Fundamentals*, NASA-TM-X-52389 | `https://ntrs.nasa.gov/citations/19680010365` | `https://ntrs.nasa.gov/api/citations/19680010365/downloads/19680010365.pdf?attachment=true` | Direct mechanism-teaching register: thrust, Newton's laws, rocket-engine fundamentals and performance factors. NASA Lewis author; NTRS marks it `Work of the US Gov. Public Use Permitted.` Older source; perform holdout memorization spot-check if assigned dev/holdout. |
| `usgs-cir-1139` | USGS | *Ground Water and Surface Water: A Single Resource*, Circular 1139 | `https://pubs.usgs.gov/publication/cir1139` | `https://pubs.usgs.gov/circ/1998/1139/report.pdf` | Explicitly described by USGS as a general educational document. Strong process explanation: hydrologic cycle, groundwater/surface-water interaction, chemical interaction, terrain effects. Avoid foreword/policy framing and audit photographs/graphics for non-USGS credits. Artifact says reprinted 1999 with revisions; record the exact revision state found in the downloaded bytes. |
| `usgs-gip-117-v3` | USGS | *Eruptions of Hawaiian Volcanoes—Past, Present, and Future*, General Information Product 117, ver. 3.0 | `https://pubs.usgs.gov/publication/gip117` | `https://pubs.usgs.gov/gip/117/gip117.pdf` | Revised October 2024; strong physical-process explanation including island origin, volcanic plumbing, eruptive style, monitoring, products and landforms. Record `revision_label` as the exact ver. 3.0 / October 2024 wording found in the artifact. Heavily illustrated; audit image credits page by page. |

## Rights posture

### FAA

FAA's handbook index states that reproduction or modification of original FAA source material is the responsibility of the publisher. Treat the prose as U.S.-government source material provisionally, but do **not** turn that agency-level posture into blanket page approval. Audit acknowledgments, photographs, manufacturer diagrams, reproduced charts, and any other credited third-party material in the exact artifact. Page-level exclusions remain mandatory where needed.

### NASA

For both NASA candidates, NTRS explicitly labels the item `Work of the US Gov. Public Use Permitted.` This is stronger than inferring public-domain status from the host. Still inspect the exact PDF for incorporated third-party figures, quotations, or separately authored material.

### USGS

USGS states that USGS-authored or produced data and information are in the U.S. public domain, while warning that some non-USGS photographs, images, and graphics may be copyrighted. That maps directly to the existing page-level `source_exclusions` contract: prose can be approved while pages containing restricted third-party material are excluded.

## Screening discriminator

For every candidate passage, ask:

> Is this passage primarily explaining a mechanism/process so the reader understands how or why it works?

Positive signals:

- causal/mechanical sequence;
- component interactions;
- present-tense explanation;
- definition followed by mechanism;
- teaching stance toward a reader who does not yet understand the system.

Reject or reclassify passages dominated by:

- recommendations or executive decisions;
- cost/benefit or policy tradeoffs;
- step-by-step operating instructions without mechanism explanation;
- standards/compliance language;
- historical narrative without technical explanation;
- tables, captions, callouts, glossaries, references, or question banks.

A useful negative test is whether the passage could naturally be headed `Recommendation for Executive Action`; if so, it is probably `business_analysis`, not `technical_explanation`.

## Extraction expectations

Do not assume the CBO or GAO artifact profile transfers to these families. Survey extraction defects independently for FAA, NASA, and USGS. Use selective correction on long/illustrated documents: base-extract the whole frozen artifact, screen structure, choose candidate target pages, then fully correct only target-bearing pages before source approval/freeze.

The widened line-break reviewer must remain advisory for alphanumeric designators and footnote interruptions. A surfaced `KEEP`, `JOIN`, `CONFLICT`, or `UNRESOLVED` verdict never changes canonical text by itself.

## Pretraining-memorization check

The two NASA candidates and Circular 1139 are old enough to plausibly appear in base-model pretraining. This is not automatically disqualifying for training, but it can weaken a held-out transformation evaluation. After deterministic source splitting is known, spot-check any older document assigned to dev/holdout for unusually verbatim model recall. If recall is clearly problematic, replace the source **before** the five-genre registry/split contract is frozen rather than manipulating its split assignment.

## Approval checklist

Apply the same source contract used for Business Analysis:

1. download the exact observed artifact; never construct a locator from an ID;
2. hash exact bytes and record `source_snapshot`;
3. confirm title/author/version from the artifact itself;
4. record revision/reissue state where present;
5. complete document-level rights/authorship review and page-level exclusions;
6. base-extract with the pinned extractor;
7. select mechanism-focused target pages/passages;
8. review extraction artifacts only on target-bearing pages;
9. regenerate canonical text and record `source_text_derivation`;
10. report heuristic passage count plus segmentation-independent prose-word volume;
11. verify no residual extraction defect occurs inside selected target pages;
12. only then change `status` from `candidate` to `approved`.
