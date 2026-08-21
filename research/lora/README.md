# LoRA research phase

This directory contains the optional open-weight adapter research path for AuthorshipShift. It is deliberately isolated from the lightweight core package.

The collapse experiment established the engineering reason to enter this phase: prompt/profile directives produced statistically detectable but practically weak changes across the corrected cross-domain study. The adapter experiment asks a new question:

> Can a learned low-rank update move the writing distribution materially farther than prompt/profile control while preserving factual fidelity and writing quality?

## First base model

The first target is `Qwen/Qwen3-8B`.

Reasons:

- dense text-generation architecture at roughly 8B parameters;
- Apache 2.0 model license;
- current Transformers support;
- compatible with PEFT/TRL;
- small enough for a realistic 4-bit QLoRA pilot on rented or notebook GPU hardware;
- no need to make the main AuthorshipShift product depend on this model.

This is a research default, not a permanent model commitment. The Engine v2 provider boundary remains model-agnostic.

## No model download by default

The training entry point is dry-run-first:

```bash
python research/lora/train_qlora.py path/to/corpus.jsonl
```

That command:

1. validates provenance and split integrity;
2. constructs the semantic-plan -> completion training rows;
3. prints the training plan;
4. does not import Torch/Transformers/PEFT/TRL;
5. does not download a model;
6. does not require a GPU.

Only this explicit form may start training:

```bash
python research/lora/train_qlora.py path/to/corpus.jsonl --execute
```

Do not use `--execute` until the corpus and holdout are frozen.

## Optional ML environment

Keep the heavyweight stack separate from the normal package:

```bash
python -m venv .venv-lora
# Windows
.venv-lora\Scripts\activate
# macOS/Linux
# source .venv-lora/bin/activate

pip install -r research/lora/requirements.txt
```

The first config is:

```text
research/lora/configs/qwen3_8b_qlora.json
```

It uses a 4-bit QLoRA-style adapter with LoRA applied to all linear layers. The values in that file are pilot defaults, not conclusions; hyperparameter changes must be versioned and compared against the same held-out evaluation.

## Training-data contract

Every line of the JSONL corpus is one object with this shape:

```json
{
  "id": "unique-example-id",
  "genre": "technical_explanation",
  "split": "train",
  "instruction": "Explain the incident clearly for a non-specialist reader.",
  "content_atoms": [
    "timeout change triggered the outage",
    "retry policy amplified severity"
  ],
  "immutable_details": ["43 minutes", "6.7%"],
  "required_qualifications": [
    "trigger and severity amplifier are distinct"
  ],
  "target_text": "Authentic target prose...",
  "provenance": {
    "kind": "user_owned",
    "source_id": "document-group-id",
    "license": null,
    "note": "optional audit note"
  },
  "metadata": {}
}
```

Allowed provenance classes:

- `user_owned`
- `consented`
- `licensed`
- `public_domain`

Licensed and public-domain records must name the applicable license/status in `provenance.license`.

Run:

```bash
python scripts/validate_lora_dataset.py path/to/corpus.jsonl
```

The validator hard-fails on:

- duplicate example IDs;
- duplicate target text;
- source documents crossing train/dev/holdout splits;
- missing provenance;
- missing license information where required;
- long target prose copied directly into the semantic plan;
- detector-oriented objective or metadata fields.

The source-document split rule is important: two paragraphs from the same document may not be divided between training and holdout merely because their text differs.

## What belongs in the targets

The preferred target is authentic human-authored prose whose use is legally and ethically clear. The training pair should be created by extracting a compressed semantic representation from that prose, then training the model to realize the content again.

The corpus should span the same broad behavior classes that Engine v2 evaluates:

- analytical argument;
- business analysis;
- technical explanation;
- science summary;
- professional writing;
- eventually additional genres not present in the original five-case experiment.

Avoid a corpus dominated by one author, source website, publication, genre, or formatting convention.

## What does not belong in the targets

Do not make the core corpus from:

- AuthorshipShift's own model-generated candidate outputs;
- AI paragraphs manually edited until a detector label changes;
- commercial-detector labels or scores;
- examples selected solely because a detector called them human;
- scraped prose with unknown rights/provenance;
- duplicated excerpts across splits.

The 100+ generated collapse-study outputs remain evaluation/research evidence, not human target data.

## Corpus stage gates

### Stage 0 — pipeline smoke

Goal: prove the schema, loader, prompt construction, and trainer operate end to end.

Use a very small set of legally usable records. Do not interpret model quality from this run.

### Stage 1 — first real adapter pilot

Before the first meaningful training run, require:

- multiple genres;
- multiple independent source documents per genre;
- document-grouped train/dev/holdout splits;
- no validator errors;
- a frozen holdout that training code never feeds into `SFTTrainer`;
- a frozen base-model evaluation generated from the same holdout prompts.

A few hundred clean examples are more useful for the first controlled pilot than thousands of poorly sourced or repetitive examples. Scale only if the adapter produces a measurable signal without fidelity regressions.

### Stage 2 — scale or stop

Compare the base model and adapter on the held-out corpus using Engine v2.

Continue scaling only if the adapter:

1. changes the intended structural/style distribution by a practically useful amount;
2. preserves immutable details and qualifications;
3. does not increase unsupported added facts/names;
4. remains strong across more than one genre;
5. does not merely learn source-specific formatting.

If those conditions fail, diagnose the dataset/objective before increasing rank, epochs, or corpus size.

## Evaluation contract

The final adapter comparison must freeze:

- base-model revision;
- adapter revision;
- evaluation prompts;
- generation settings;
- random seeds where the runtime supports them;
- held-out documents;
- candidate count per condition;
- fidelity/gate thresholds.

The primary comparison is base vs adapter under identical conditions. The existing prompt-profile collapse experiment becomes contextual evidence rather than the training loss.

Commercial detector results may be recorded later as external checkpoint metadata. They are not a training objective or a criterion for selecting training examples.
