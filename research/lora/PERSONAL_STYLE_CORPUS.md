# Personal-style corpus track

The general AuthorshipShift adapter and the personal-style experiments answer different questions and remain separate evaluation tracks.

## Experiment design

Two personal experiments are defined.

### Experiment A — natural voice

Use only documents the user can identify as substantially self-authored without material AI drafting assistance. This experiment asks whether adaptation moves generation toward the user's unaided writing distribution while preserving semantic fidelity.

### Experiment B — accepted academic voice

Use user-authored coursework that the user deliberately finalized/accepted, regardless of whether AI assistance was absent, material, or unknown. AI-assistance status is preserved as provenance metadata but is not an inclusion criterion for Experiment B.

Experiment B asks whether adaptation can reproduce the distribution of academic prose the user historically selected and accepted as representative of their submitted work. Detector scores are neither stored nor optimized.

For both experiments, compare the adapted model against the same unadapted base model on held-out semantic plans. A later general-adapter comparison may be added once the five-genre corpus is complete.

## Provenance classes

Personal documents use one of these corpus-level provenance classes:

- `self_authored` — substantially written by the user;
- `ai_assisted_accepted` — AI materially contributed, but the user selected/edited/accepted the finished work;
- `other_author` — written by another person and never eligible as a personalization target;
- `unclassified` — provenance is not yet resolved.

All personal source artifacts use:

```json
"provenance_kind": "user_owned"
```

AI-assistance status remains an independent field. Do not infer it from style classifiers or detector scores.

## Frozen Experiment B corpus

Experiment B is frozen before semantic-plan annotation begins. The local manifest pins:

- exact source artifact SHA-256 values;
- document-level train/holdout membership;
- target-eligible paragraph/region masks;
- exclusions for other-author material and reproduced regions;
- the frozen corpus hash.

The split is document-level. No paragraph from a holdout document may become a training target.

If a portfolio reproduces a standalone document verbatim, exclude the duplicated region from one side of the corpus before annotation. Duplicate target text must not cross train/holdout boundaries.

## Lightweight personal annotation contract

The personal corpus does **not** reuse the full page-scoped PDF correction contract unless the source actually requires it. The personal artifacts are short, user-owned, and already audited at paragraph/region granularity. Requiring page numbers, rights scans, and long-document correction ledgers for clean DOCX text would add ceremony without strengthening the experiment.

The personal contract is:

```text
immutable source artifact SHA-256
→ deterministic format-specific extraction
→ immutable extracted-text SHA-256
→ frozen paragraph/region inclusion mask
→ semantic plan + constraints
→ immutable target text
```

The following invariants remain mandatory:

1. **Exact artifact identity.** Every source target traces to the original frozen DOCX/PDF artifact hash.
2. **Deterministic extraction.** The extractor name/version and extraction mode are pinned. Re-extraction from the same artifact must reproduce the same extracted-text hash.
3. **Immutable target regions.** Each training example records the source document and exact paragraph/region identifiers used as its target. Excluded regions can never become targets without creating a new corpus contract.
4. **Target fidelity.** Target text is copied from frozen eligible source regions. Cleaning may remove structural wrapper text but must not rewrite the user's prose.
5. **Document-level split isolation.** Train and holdout membership is frozen before semantic-plan generation.
6. **Duplicate/near-duplicate gates.** Exact and strong near-duplicate targets across train/holdout remain fatal.
7. **Frozen annotation packets.** Once a semantic plan is reviewed and frozen, the target text, source identifiers, split, and inclusion mask cannot silently change.
8. **No detector objective.** Detector scores are not corpus labels, training targets, reward signals, or evaluation gates.

## DOCX extraction

For DOCX, use a pinned OOXML extraction path rather than converting to PDF. Preserve paragraph ordering and stable paragraph identifiers. Extract body text plus any relevant tables/footnotes/endnotes/header/footer content needed for authorship review, but only frozen target-eligible body regions may become training targets.

The extractor must record at least:

```json
{
  "extractor_name": "<pinned implementation>",
  "extractor_version": "<version>",
  "artifact_sha256": "<source hash>",
  "extracted_text_sha256": "<derived text hash>"
}
```

Do not normalize spelling, grammar, punctuation, capitalization, or sentence structure. Natural imperfections are part of the writing distribution.

The pinned implementation is `personal-docx` `v1` in `authorship_shift.personal_extraction`. It reads `word/document.xml`, then `word/comments.xml`, then header/footer parts, in that order; emits non-empty paragraphs in document order; renders `w:tab`, `w:br` and `w:cr` as one space each; and records `part`, paragraph style, and whether the paragraph sits in a table. Region identifiers are `<source_id>:b<NNNN>`, where the ordinal is the document-order block index the frozen region mask already refers to. `extracted_text_sha256` is the SHA-256 of the newline-joined region texts.

## PDF fallback

If a personal PDF already has a clean text layer and stable paragraph extraction, it may use the same lightweight region contract with a pinned PDF extractor. If extraction artifacts materially alter target prose, escalate that source to the full canonical PDF correction workflow used by the general corpus.

Escalation is source-specific; one problematic PDF does not force every personal document through page-scoped derivation machinery.

`assess_pdf_text_layer` decides cleanliness against the pinned `pypdf==6.15.0` text layer. Two artifacts disqualify a source, because both change eligible target prose rather than only its presentation:

- shredded lines, where a renderer emits roughly one word per line, so paragraph boundaries are not recoverable;
- doubled intra-line spacing, so word spacing no longer matches the source prose.

A failing assessment means that source escalates. It never licenses repairing the text in place under the light contract.

## Semantic-plan annotations

Training examples use the same conceptual representation as the general adapter:

```text
semantic plan + immutable constraints → authentic target realization
```

Plans describe **what the passage says**, not how to imitate its surface wording. At minimum capture:

- content atoms;
- immutable factual/details constraints;
- required qualifications or caveats;
- intended communicative function when it is necessary to understand the passage.

Do not put stylistic instructions such as "write like Thomas" into the semantic plan. The target distribution, not the prompt, should supply the personalization signal.

Model-assisted plan extraction is allowed only as a draft. It remains `needs_review` until checked against the target passage. The semantic plan must not introduce facts absent from the target.

For very short adjacent paragraphs that form one indivisible thought, a multi-paragraph target is allowed. The source region identifiers must make that grouping explicit and deterministic.

## Holdout evaluation

Holdout documents never receive training targets. They are used to create evaluation semantic plans only after the split is frozen.

Primary checks:

- semantic fidelity to the held-out plan;
- distributional similarity to held-out user prose;
- sentence and paragraph structure;
- lexical and syntactic tendencies;
- generalization across topics;
- suspicious verbatim overlap with training data.

A strong result is closer behavior on unseen semantic plans without reproducing held-out wording or memorizing training passages.

## Storage

Raw school work, extracted prose, local manifests, annotations, and datasets remain under gitignored local corpus/annotation/dataset paths. Public Git contains only tooling, schemas, aggregate metrics, experiment protocols, and non-sensitive documentation.

## Engineering rule

Do not add general-purpose infrastructure merely because a theoretical edge case exists. Add or harden machinery only when a real personal-corpus artifact exposes a reproducibility, authorship, leakage, or fidelity failure that can affect the experiment.
