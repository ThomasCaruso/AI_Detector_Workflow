# Personal-style corpus track

The general AuthorshipShift adapter and the personal-style adapter answer different questions and should remain separate experiments.

## Experiment design

Evaluate three systems on the same held-out semantic plans:

1. **Base model** — unadapted open-weight model.
2. **General adapter** — trained on the five-genre human-writing corpus.
3. **Personalized adapter** — starts from the general adapter and receives an additional user-owned writing corpus.

The purpose of the personal track is to test whether authentic user-authored prose moves generation toward that writer's natural realization patterns while semantic fidelity remains clean. It is not a substitute for the five-genre corpus, because a single writer cannot provide the independent source diversity needed for the general writing experiment.

## Preferred sources

Prioritize genuinely user-authored prose, especially material written before routine AI-assisted drafting. Useful examples include:

- essays and research papers;
- finance/business assignments;
- history or humanities papers;
- reports and case analyses;
- discussion posts and long-form responses;
- other sustained prose the user can confidently identify as their own writing.

Older work is especially valuable because it provides a cleaner estimate of the writer's unaided distribution.

## Provenance

Register personal documents as:

```json
"provenance_kind": "user_owned"
```

Each source still requires an exact artifact snapshot. Preserve the original artifact rather than copying text into the public repository.

For each document, record in local notes whether the prose was:

- written without AI assistance;
- lightly AI-assisted (for example proofreading only);
- materially AI-assisted;
- uncertain.

For the first personal experiment, prefer the first category. Materially AI-assisted documents should not be treated as clean evidence of the user's natural writing distribution.

## What is excluded

Exclude text not authored by the user, including:

- assignment prompts and rubrics;
- professor/teacher comments;
- quotations and block quotes;
- copied source passages;
- bibliographies/reference lists;
- boilerplate templates;
- collaborator-written sections;
- generated text that the user did not substantially author.

Citations and factual details may remain inside otherwise user-authored prose when they are naturally part of the writing, but source text itself must not be mistaken for target voice.

## Splitting and evaluation

Split at the **document** level, never by paragraph. All passages from one school paper belong to one split.

Prefer a temporally and topically meaningful holdout when possible: keep several entire documents unseen during training, ideally from different courses/topics than the training documents.

The held-out personal set is used to measure:

- semantic fidelity;
- style distance to authentic user prose;
- sentence/paragraph structure and lexical tendencies;
- generalization to new topics;
- suspicious verbatim memorization.

A strong result is not reproduction of held-out wording. It is closer distributional behavior on new semantic plans while long verbatim overlap remains low.

## Memorization control

Do not train on every available personal document. Reserve complete documents for evaluation before annotation begins. Once a personal document enters the training split, it cannot later be promoted to holdout.

Use the existing duplicate/near-duplicate gates across training and holdout targets. If multiple assignments reuse the same template, prompt, or substantial prose, treat them as related sources and prevent leakage across the boundary.

## Storage

Raw school work, extracted prose, annotations, and datasets stay under the existing gitignored local corpus/annotation/dataset paths. Public Git contains only tooling, schemas, aggregate metrics, and non-sensitive experiment documentation.

## Do not add new ingestion machinery yet

The first batch of real user documents determines whether additional extraction support is needed. PDFs can use the existing frozen PDF derivation path. Plain text can use the existing artifact snapshot path. If the first useful corpus contains DOCX or another format whose text extraction is not reproducibly covered, define and pin that derivation only then rather than speculating in advance.
