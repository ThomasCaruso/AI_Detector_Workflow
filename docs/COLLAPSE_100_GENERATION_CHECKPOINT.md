# 100-generation collapse checkpoint

Date: 2026-08-21

This checkpoint records the first completed five-domain, 5-profile x 4-sample experiment before repairing the two remaining case-level confounds. The generated outputs themselves remain outside version control; the numbers below are descriptive experimental history supplied from the completed run.

## First complete matrix

| Domain | Within | Between | Ratio | p | Gate | Reading |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Technical explanation | 0.0823 | 0.0801 | 0.973 | 0.7091 | pass | collapsed |
| Business analysis | 0.0859 | 0.0962 | 1.120 | 0.0575 | pass | weak |
| Analytical argument | 0.0667 | 0.0794 | 1.190 | 0.0065 | pass, vacuous fidelity evidence | weak |
| Science summary | 0.0665 | 0.0816 | 1.227 | 0.0010 | pass | weak |
| Professional writing | 0.0565 | 0.0932 | 1.651 | fail | separated, confounded |

The four non-confounded ratios lie between 0.973 and 1.227, with a mean of approximately 1.13. None exceeds the project's 1.25 useful-steering threshold. Science also demonstrates why statistical significance is not sufficient by itself: p=0.0010 accompanies a ratio of only 1.227.

## Why the first Professional result cannot vote

The Professional batch contained a format split aligned with the profile labels. All four direct-plain candidates omitted email furniture while the other profiles included a subject line and/or greeting/sign-off. The same direct-plain outputs were also the shortest. The resulting 1.651 ratio therefore mixes prose shape with document furniture and is not evidence that the profile directives controlled the underlying writing distribution.

The original fidelity gate also treated `The Atlas` as an exact multiword name even though `The` is the sentence article and the product name is `Atlas`. The repaired precheck strips a leading article from this form and protects `Atlas` itself.

Professional case revision 2 now requires body text only: no subject line, greeting, salutation, signature, or sign-off. The target remains approximately 150 words. The domain must be regenerated under that fixed contract before it can vote.

## Why the first Analytical result cannot vote

The original analytical source contained no checkable literal immutables, so `fidelity_evidence=vacuous`. The ratio is useful as a descriptive style measurement but cannot become a trusted cross-domain voter under the final-verdict guard.

Case revision 2 adds one explicitly hypothetical, non-causal illustration with 18-month and 12-month development-cycle constraints. These values exist only to make literal preservation checkable; the prompt states that they are illustrative and not evidence that competition caused the change. The repaired case must be regenerated before it can vote.

## Added-detail failure discovered in the first Analytical run

One evidence-first candidate introduced `Sony` and `Toshiba`, neither of which appeared in the locked source. The immutable precheck could not detect that because it only asked whether source details survived.

The fidelity instrumentation now also performs a conservative added-name check. A TitleCase-like identifier introduced inside a sentence and absent from the source is a hard failure. Sentence-initial capitalization and acronyms such as `AI`, `R&D`, `EV`, and `API` are deliberately excluded from this regex precheck. This is not a general fact checker; it closes the observed high-confidence fabrication mode without pretending to verify arbitrary new claims.

## Rerun protocol

Only two domains require new generations:

- `professional_email_001`, revision 2: 5 profiles x 4 samples = 20 fresh generations;
- `competition_innovation_001`, revision 2: 5 profiles x 4 samples = 20 fresh generations.

The existing Technical, Business, and Science measurements remain valid because their case definitions are unchanged.

The old Professional and Analytical outputs must not be analyzed under the revised manifests. Prepare fresh prompts and clear only those two domains' old outputs before generating the 40 replacements. Keep model surface, wrapper, fresh-context policy, profile definitions, and sampling behavior unchanged.

## Decision rule after rerun

Do not override the guard. Re-run the five-domain report with the two repaired batches. If the repaired Professional and Analytical domains also remain below the useful-steering threshold with clean fidelity gates, the evidence supports moving research beyond prompt/profile control and into the open-weight/LoRA phase. If either produces reproducible, uncontaminated separation above the threshold, preserve that domain-dependent result and scope later tuning accordingly.

External detector spend remains zero at this checkpoint.
