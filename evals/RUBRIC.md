# Portable Skill Evaluation Rubric

Use this rubric to evaluate AuthorshipShift outputs without treating any external detector as ground truth.

Score each dimension from 0 to 2. A strong candidate should score 2 on fidelity and at least 1 on every other dimension before external observations are even considered.

## 1. Semantic fidelity

- **0** — changes, drops, or invents material claims.
- **1** — preserves the main point but weakens a qualification, comparison, or causal distinction.
- **2** — preserves all required claims, qualifications, causal relationships, and conclusions.

Fidelity is a gate. A candidate that scores 0 should be rejected regardless of stylistic quality.

## 2. Immutable-detail fidelity

- **0** — changes or loses names, numbers, dates, quotations, citations, or technical labels.
- **1** — mostly correct but contains a minor immutable-detail problem.
- **2** — all immutable details are preserved exactly where required.

## 3. Architectural independence

- **0** — source-order paraphrase; opening and support sequence remain substantially unchanged.
- **1** — some restructuring, but the source architecture is still obvious.
- **2** — the piece has been rebuilt around the subject while preserving the content lock.

## 4. Rhetorical naturalness

- **0** — highly regular essay pattern: thesis → evenly spaced reasons → caveat → restated thesis.
- **1** — mostly natural but still contains visible template-level regularity.
- **2** — rhetorical sequence follows the material rather than a generic composition template.

## 5. Transition economy

- **0** — repeated signposting announces most rhetorical moves.
- **1** — some unnecessary transition scaffolding remains.
- **2** — transitions appear only where the relationship would otherwise be unclear.

## 6. Cadence and construction diversity

- **0** — repeated mirrored clauses, enumerations, colon summaries, or matching sentence shapes dominate the passage.
- **1** — a few repeated constructions are noticeable.
- **2** — sentence shapes follow their logical functions without obvious mechanical repetition.

This does not reward random sentence-length variation, deliberate fragments, or errors.

## 7. Emphasis allocation

- **0** — every requested subpoint receives mechanically equal treatment.
- **1** — some prioritization is visible.
- **2** — the most consequential or difficult ideas receive more space while secondary requirements remain intact.

## 8. Opening and ending quality

- **0** — generic opening and polished thesis-restatement ending.
- **1** — either the opening or ending is well chosen, but the other remains formulaic.
- **2** — the opening establishes the most useful entry point and the ending stops where the argument actually lands.

## 9. Voice fit

When no user sample exists, score general fit to the requested tone.

- **0** — tone conflicts with the request or becomes conspicuously inflated.
- **1** — acceptable but generic.
- **2** — diction, density, formality, and sentence shape fit the requested context.

## 10. External detector observations

If the user chooses to test a passage with an authorship or AI detector, record the result separately from the rubric. Do not convert the detector score into a rubric score, do not treat it as proof of authorship, and do not alter the skill specifically to target a named detector.

External observations can indicate that two drafts differ in ways worth investigating, but the development target remains writing quality, structural naturalness, and fidelity.