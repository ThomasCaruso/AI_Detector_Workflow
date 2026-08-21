# ADR 0002: Enter the LoRA / open-weight research phase

Status: Accepted

Date: 2026-08-21

## Decision

AuthorshipShift will move from prompt/profile-only control into an open-weight adapter research phase.

The portable Skill remains the user-facing interface. Engine v2 remains the evaluation, fidelity, and candidate-selection layer. A trainable open-weight generator becomes a new provider behind that engine rather than replacing the existing architecture.

The first training target is `Qwen/Qwen3-8B` using PEFT/QLoRA-style supervised fine-tuning. The initial experiment is intentionally model- and provider-isolated: the base model and adapted model must be evaluated with the same prompts, generation surface, fidelity gates, and collapse diagnostics.

## Evidence

The corrected cross-domain collapse experiment used five generation profiles with four independent samples per profile. The final clean measurements were:

| Domain | Within | Between | Ratio | p | Gate | Reading |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| Technical explanation | 0.0823 | 0.0801 | 0.973 | 0.7091 | pass | collapsed |
| Analytical argument | 0.0648 | 0.0722 | 1.113 | 0.0230 | pass | weak |
| Business analysis | 0.0859 | 0.0962 | 1.120 | 0.0575 | pass | weak |
| Professional writing | 0.0719 | 0.0872 | 1.213 | 0.0020 | fail on length | weak |
| Science summary | 0.0665 | 0.0816 | 1.227 | 0.0010 | pass | weak |

Four trusted domains span 0.973–1.227. No uncontaminated domain reaches the predeclared 1.25 threshold for useful profile steering. The professional-writing rerun also demonstrated that an earlier 1.651 ratio was caused by document furniture rather than prose distribution: after fixing format, the ratio fell to 1.213.

The result is therefore not that profile directives have no effect. Several effects are statistically detectable. The result is that the effects are too small and inconsistent to provide the level of generation control the project requires.

## Why not increase prompt samples again

The project already corrected three major experimental problems before accepting this conclusion:

1. 5×2 batches were shown by direct replication to be unstable; the design was increased to 5×4.
2. Template-induced formatting differences were removed and rerun.
3. Fidelity precheck false positives and unsupported added-name failures were repaired and re-analyzed from frozen outputs.

The remaining ratios cluster tightly around a weak effect. Additional prompt-level samples would mostly estimate that weak effect more precisely rather than test a new intervention.

## Why Qwen3-8B first

The first adapter target should be small enough for practical QLoRA experiments, widely supported by the Hugging Face training stack, and permissively licensed. Qwen3-8B is a dense ~8B-parameter causal language model released under Apache 2.0 and is supported by Transformers. Larger contemporary models such as Mistral Small 4 use substantially more total parameters and are poor first targets for a low-cost adapter experiment.

This is a research default, not a permanent product dependency. Engine v2 must keep the generator boundary provider-agnostic.

## Training objective

The adapter is trained for writing behavior, not for a commercial detector score.

Training examples pair a semantic/content representation with an authentic target realization. Targets must be user-owned, licensed, consented, or otherwise legally usable human-authored text. The dataset should teach:

- structural variety;
- subject-specific lexical choice;
- non-formulaic discourse organization;
- natural cadence variation;
- preservation of factual details and certainty;
- adherence to requested genre and length.

The preferred representation is:

`semantic plan + constraints -> target human realization`

Do not build the core corpus as:

`model output -> detector-passing rewrite`

The latter entangles the training objective with one model's artifacts and encourages shallow replacement rules.

## Experimental contract

The first adapter experiment must compare at least:

1. frozen base model;
2. LoRA/QLoRA adapter on the same base model.

Both arms must use the same held-out evaluation cases and generation settings. The adapter is a success only if it improves the intended writing-distribution metrics while keeping fidelity and quality gates at least as strong as the base model.

Commercial detector observations may be recorded later as external checkpoint metadata, but they are not a training loss, reranking target, or routine development signal.

## No-go conditions

Do not advance an adapter because it merely:

- raises stylistic distance while losing facts;
- increases lexical novelty while degrading clarity;
- introduces unsupported names or examples;
- exploits formatting differences;
- overfits the five seed cases;
- improves a commercial detector score while regressing the project's own quality/fidelity gates.

## Next milestones

1. Define and validate the training-data schema and provenance rules.
2. Build a small, legally usable pilot corpus across multiple writing domains.
3. Add a dry-run QLoRA training entry point with no model download or GPU use by default.
4. Freeze a held-out adapter evaluation set that is disjoint from the training corpus.
5. Train the first adapter only after the dataset and evaluation contracts pass locally.
6. Compare base vs adapter with Engine v2 and the collapse/fidelity diagnostics before any external detector checkpoint.
