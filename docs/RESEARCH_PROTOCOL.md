# Research Protocol

AuthorshipShift treats commercial detector calls as held-out measurements rather than an optimization signal.

## Core hypotheses

1. Document-level composition changes can produce larger distributional shifts than sentence-level paraphrasing.
2. Generator-family diversity matters because model and post-training distributions differ.
3. Semantic fidelity and writing quality must remain hard constraints.
4. Repeated black-box querying risks overfitting to a detector and weakens the research claim.

## Five-query protocol

The default project budget is five external Pangram 4 evaluations:

1. Untouched baseline generation.
2. Best single-stage natural-writing candidate.
3. Best full pipeline candidate selected without Pangram feedback.
4. Winning pipeline on an unseen topic or genre.
5. Frozen blind-validation candidate from the held-out corpus.

A tested candidate must be frozen before the score is logged. The software enforces this by default.

## Development measurements

Development may use:

- semantic-fidelity judge outputs
- deterministic claim-coverage warnings
- immutable-item checks
- writing-quality judge outputs
- pairwise lexical/structural diversity
- lineage and generator-family metadata

None of these are represented as a reconstruction of Pangram.

## Reporting

For every external result record:

- detector and version
- candidate ID
- score and label
- test date
- whether the candidate was frozen beforehand
- any known detector settings
- experiment stage

Do not revise a tested candidate and reuse the same candidate ID.
