# Human corpus and semantic-plan pipeline

The first adapter experiment trains on **semantic plan -> authentic human prose**.
The corpus is not built from detector labels and is not built by recycling the
model outputs that demonstrated the prompt/profile ceiling.

## 1. Register source documents

Copy the template locally:

```bash
cp research/lora/source_registry.example.json research/lora/local_corpus/source_registry.json
```

Every document gets one stable `source_id`. Mark it `approved` only after the
exact document has been reviewed for rights/provenance. Agency-level public-domain
policies are evidence to inspect, not blanket approval for every item hosted on an
agency website.

A source document belongs to exactly one genre for the initial experiment. If a
single document contains materially different writing modes, create separate
source IDs only when they represent independently identifiable documents/sections
with clear provenance; do not split one document merely to manipulate train/dev/
holdout assignment.

Rights-clean is not the same as style-clean. A reproduced comment letter,
contractor-authored appendix, quoted third-party passage, or other distinct authorial
voice can be legally usable while still contaminating the writing distribution the
adapter is meant to learn. Exclude those passages unless that distinct voice is
itself an intentional, separately registered source for the target genre.

Every **approved** source must also pin the exact artifact reviewed for excerpting:

```json
"source_snapshot": {
  "retrieved_at": "2026-08-21T23:30:00Z",
  "sha256": "<64 hex digits>",
  "artifact_kind": "pdf",
  "revision_label": "optional exact revision/version label"
}
```

This applies to public-domain, licensed, user-owned, and consented sources alike.
Rights determine whether the text may be used; the snapshot identifies which bytes
were actually reviewed. Use:

```bash
python scripts/hash_source_artifact.py path/to/reviewed-file.pdf --artifact-kind pdf
```

For revised documents, record the exact revision label when one is published. The
canonical URL can remain stable while the underlying document changes; the SHA-256
is what freezes the reviewed artifact state.

`document_locator` should record the **observed** artifact URL/filename, DOI/report
number, or stable local locator used during review. Do not construct a PDF URL or
artifact filename from a publication number merely because a source site often
follows that pattern. Home-page IDs, HTML document-node IDs, and downloadable
artifact names are separate identifiers unless the exact source proves otherwise.

The initial adapter experiment has five target genres:

```text
business_analysis
technical_explanation
science_summary
professional_writing
analytical_argument
```

**Freeze the real source registry before annotation starts.** The decision-grade
splitter ranks approved source documents within each genre using the frozen split
seed and the complete approved registry. Adding or removing an approved source is
therefore a new split contract, not an incremental edit to an existing annotation
set.

The splitter's technical minimum is three approved source documents per genre, which
is enough to create one train, one dev, and one holdout source. The first real
adapter pilot uses a stricter **hard structural floor of at least six independent
approved documents per genre**. No number of additional excerpts from one document
substitutes for document independence.

See `SOURCE_POOLS.md` for bootstrap source pools and their rights-policy links.

## 2. Canonically derive text from frozen PDF artifacts

A frozen PDF hash does not by itself determine `target_text`. PDF text extraction
can vary by extractor/version and can introduce artifacts such as ligatures,
intra-word spacing, and visual-line hyphenation. Therefore an approved PDF must
have a frozen `source_text_derivation` before annotation packets can be created.

The first canonical PDF recipe is:

```text
extractor_name       = pypdf
extractor_version    = 6.15.0
extraction_mode      = plain
normalization_version = pdf-text-v1
```

Install the isolated extraction dependency:

```bash
pip install -r research/lora/extraction-requirements.txt
```

Run a base extraction from the exact hashed artifact:

```bash
python scripts/extract_source_text.py \
  research/lora/local_corpus/artifacts/62265-federal-credit-programs.pdf \
  research/lora/local_corpus/extracted/cbo-62265.canonical.json \
  --source-id cbo-62265
```

`pdf-text-v1` performs only source-agnostic cleanup:

- normalize line endings;
- expand standard Unicode presentation ligatures such as `ﬀ -> ff`;
- normalize Unicode spacing characters/tabs to normal spaces;
- collapse repeated horizontal spaces and remove trailing spaces.

It deliberately does **not** guess ambiguous repairs. In particular, it does not
silently turn `T reasury` into `Treasury` or `guar-\nantees` into `guarantees`.
Those changes may be correct for one PDF and wrong for another.

If the base extraction contains such artifacts, create a reviewed correction
ledger:

```bash
python scripts/init_text_corrections.py \
  research/lora/local_corpus/extracted/cbo-62265.canonical.json \
  research/lora/local_corpus/extracted/cbo-62265.corrections.json
```

Then add page-scoped exact replacements, for example:

```json
{
  "schema_version": 1,
  "artifact_sha256": "<frozen PDF SHA-256>",
  "base_text_sha256": "<base extraction SHA-256>",
  "replacements": [
    {
      "page": 2,
      "old": "T reasury",
      "new": "Treasury",
      "expected_count": 1
    },
    {
      "page": 3,
      "old": "guar-\nantees",
      "new": "guarantees",
      "expected_count": 1
    }
  ]
}
```

Re-run extraction with the ledger:

```bash
python scripts/extract_source_text.py \
  research/lora/local_corpus/artifacts/62265-federal-credit-programs.pdf \
  research/lora/local_corpus/extracted/cbo-62265.canonical.json \
  --source-id cbo-62265 \
  --corrections research/lora/local_corpus/extracted/cbo-62265.corrections.json
```

The correction ledger is bound to both the artifact SHA-256 and the base extracted
text SHA-256. Every replacement is page-scoped and carries an expected occurrence
count, so extraction drift causes a hard failure instead of applying a patch to the
wrong text.

Populate the local registry with the resulting contract:

```json
"source_text_derivation": {
  "artifact_sha256": "<same SHA-256 as source_snapshot>",
  "extractor_name": "pypdf",
  "extractor_version": "6.15.0",
  "extraction_mode": "plain",
  "normalization_version": "pdf-text-v1",
  "base_text_sha256": "<from extract_source_text.py>",
  "corrections_sha256": "<hash or null>",
  "canonical_text_sha256": "<from extract_source_text.py>",
  "canonical_text_path": "extracted/cbo-62265.canonical.json"
}
```

`canonical_text_path` is relative to the local registry directory. Canonical text
and correction ledgers remain under `research/lora/local_corpus/` and are not
committed.

Annotation preparation verifies that:

1. the derivation references the same PDF SHA-256 as `source_snapshot`;
2. extractor/version/mode/normalization match the frozen recipe;
3. the local canonical file hashes to the recorded `canonical_text_sha256`;
4. each raw `target_text` is a substring of canonical text after **whitespace-only
   reflow**.

Character-level cleanup outside the reviewed correction ledger is rejected. The
frozen annotation manifest includes the text-derivation contract, so changing the
extractor version, correction hash, or canonical-text hash after preparation
invalidates the packet.

## 3. Create raw excerpt JSONL locally

Raw text is gitignored. One line per excerpt:

```json
{"id":"usgs-001-p12-a","source_id":"usgs-001","genre":"science_summary","instruction":"Summarize the finding in plain analytical prose.","target_text":"<human prose>","excerpt_locator":"p. 12, paragraphs 2-3","metadata":{}}
```

Rules:

- for PDF sources, copy `target_text` from the frozen canonical extraction, with
  whitespace-only reflow permitted;
- do not independently de-hyphenate, repair extraction artifacts, improve,
  simplify, paraphrase, or clean the target text;
- if the canonical extraction is wrong, fix the reviewed correction ledger,
  regenerate canonical text, and update its hashes **before** creating packets;
- keep enough surrounding context in `excerpt_locator` to audit the excerpt;
- exclude quotations or sections written by a different authorial voice unless
  that voice is intentionally registered as its own source, even when rights are
  otherwise clean;
- exclude tables, captions, boilerplate, references, navigation text, and image
  descriptions;
- prefer sustained prose of roughly 80-500 words for the first corpus.

Passage yield is measured rather than assumed. The first frozen CBO business source
(`cbo-62265`) yielded at least 11 clean 80-500-word passages, showing that a fixed
"3-5 passages per document" expectation is too restrictive. For the first pilot,
use two separate corpus constraints:

- **hard structural floor:** at least 6 independent approved documents per genre;
- **provisional volume target:** at least 25 clean passages per genre.

The first is structural and cannot be waived by high-yield documents. The second is
an empirical starting target and should be revisited after multiple source types and
genres have been audited.

## 4. Freeze genre-stratified source splits and prepare annotation packets

```bash
python scripts/prepare_lora_annotations.py \
  research/lora/local_corpus/raw_excerpts.jsonl \
  research/lora/local_corpus/source_registry.json \
  research/lora/annotations
```

The default split strategy is `genre-stratified-hash-v1`:

1. consider approved source documents only;
2. group them by target genre;
3. hash-rank `source_id` values within each genre using the frozen split seed;
4. reserve at least one source document for dev and one for holdout in every
   target genre;
5. assign the rest to train.

With six source documents in a genre, the default 80/10/10 target becomes 4 train
/ 1 dev / 1 holdout. With ten documents it becomes 8 / 1 / 1. The exact minority
counts are deterministic and rounded from the configured fractions while always
reserving at least one training source.

Every excerpt from one source document receives that document's split. The split
planner reports two separate fingerprints:

- `registry_split_sha256` — document identities and their exact split assignment;
- `source_snapshot_set_sha256` — the exact reviewed artifact versions.

Annotation preparation copies each source snapshot and text-derivation contract into
packet metadata **before** the frozen annotation manifest is written. Changing the
target, provenance, split, source artifact hash, extractor contract, corrections
hash, or canonical-text hash afterward invalidates the frozen contract.

A tiny smoke fixture can bypass the coverage requirement only explicitly:

```bash
python scripts/prepare_lora_annotations.py ... --allow-incomplete-genre-coverage
```

That mode is diagnostic only and must not be used for a training decision.

The generated packets contain the authentic target prose but deliberately leave
these fields empty:

```text
content_atoms
immutable_details
required_qualifications
```

Nothing automatically derives a semantic plan from the target. That is an
intentional leakage control.

## 5. Semantic-plan annotation

### Manual path

For each packet, describe the information in the target without copying its prose.
When review is complete, explicitly set:

```json
"metadata": {"annotation_status": "ready", ...}
```

### Optional model-assisted path

To reduce annotation labor without allowing a model to approve its own training
input:

```bash
python scripts/prepare_semantic_plan_batch.py \
  research/lora/annotations \
  research/lora/local_corpus/plan_batch
```

Run each generated prompt independently in a model surface if desired and save
JSON only to the matching `*.response.json` file. Then ingest:

```bash
python scripts/ingest_semantic_plan_batch.py \
  research/lora/local_corpus/plan_batch
```

The response parser accepts only semantic-plan fields. It cannot overwrite
`target_text`, `split`, provenance, or packet metadata. Ingested suggestions are
marked:

```text
annotation_status = needs_review
plan_extraction_method = model_assisted
```

They are **not training examples** until a human reviewer checks semantic
sufficiency, removes unsupported details or copied phrasing, and explicitly marks
the packet `ready`.

### content_atoms

Use short propositions representing the ideas/facts the realization must express.
Aim for 2-8 atoms for normal excerpts. Atoms should be semantically sufficient but
lexically compressed.

Bad:

```text
The report separates the measured pattern from the mechanisms that might explain it.
```

Better:

```text
observed pattern is distinct from proposed mechanisms
```

### immutable_details

Use only surface details whose exact identity materially matters: numbers, dates,
product/person/organization names, technical identifiers, named programs, etc.
Do not put ordinary phrases here just because they occur in the target.

### required_qualifications

Record uncertainty, causality limits, scope restrictions, counterpoints, or other
qualifications that must survive realization.

The existing LoRA dataset validator checks **all prompt-bearing fields** for long
verbatim spans copied from `target_text`. A completed packet that leaks target prose
will fail compilation.

## 6. Compile and validate

Diagnostic compile:

```bash
python scripts/build_lora_dataset.py \
  research/lora/annotations \
  research/lora/datasets/lora_v1.jsonl
```

Decision-grade compile before training:

```bash
python scripts/build_lora_dataset.py \
  research/lora/annotations \
  research/lora/datasets/lora_v1.jsonl \
  --require-trainable
```

The second form refuses to produce a trainable corpus unless:

- train, dev, and holdout are globally non-empty; **and**
- every one of the five target genres has at least one ready example in train,
  dev, and holdout.

The QLoRA runner independently checks the same genre x split requirement before
heavy imports, model download, or GPU initialization when `--execute` is supplied.

## 7. Audit the corpus

```bash
python scripts/audit_lora_dataset.py \
  research/lora/datasets/lora_v1.jsonl \
  --json-out research/lora/local_corpus/corpus_audit.json
```

The audit reports:

- examples and words by genre;
- examples by global split;
- **examples by genre x split**;
- **unique source documents by genre x split**;
- every missing target genre x split cell;
- examples and words by provenance kind;
- examples and words by source document;
- largest source-document share;
- near-duplicate target prose using word 5-gram Jaccard similarity;
- near-duplicates that cross train/dev/holdout boundaries.

The audit exits non-zero when the decision-grade genre x split matrix is
incomplete. A diagnostic-only escape hatch exists:

```bash
python scripts/audit_lora_dataset.py ... --allow-incomplete-genre-coverage
```

Defaults also warn when one source exceeds 15% of examples or words and when a
genre has fewer than five examples. Those are corpus-design warnings rather than
model hyperparameters; tune them only with an explicit corpus rationale.

## 8. Validate without training

```bash
python scripts/validate_lora_dataset.py research/lora/datasets/lora_v1.jsonl
python research/lora/train_qlora.py research/lora/datasets/lora_v1.jsonl
```

The dry run reports genre x split coverage but remains diagnostic: it does not
require a complete corpus and still performs no model download or heavy import.
`--execute` is stricter and refuses training unless the full five-genre split
contract is satisfied.

## Initial corpus target

Do not optimize for a large number of excerpts immediately. The first real adapter
pilot uses:

```text
5 target genres
>= 6 independent approved source documents per genre   HARD FLOOR
>= 25 clean passages per genre                         PROVISIONAL TARGET
multiple provenance/source pools where practical
train/dev/holdout represented inside every genre
```

The six-document floor protects out-of-sample independence. The 25-passage target
is deliberately provisional and should move only in response to measured passage
yield and adapter learning behavior. A single high-yield report can satisfy much of
the volume target but can never substitute for independent documents.

This corpus is for a first *pipeline and overfit-risk experiment*, not enough to
claim a production-quality writing adapter. The first training question is simply
whether the adapter moves held-out style behavior while the fidelity gates remain
clean **in every genre**, rather than only in a globally pooled holdout.

## What stays out of Git

The repository ignores:

```text
research/lora/local_corpus/
research/lora/annotations/
research/lora/datasets/
```

Do not override those ignores merely because a source is public domain. Keeping
training text local prevents accidental provenance mixing, keeps private/user-owned
material out of the public repository, and makes source manifests/hashes the
reviewable artifacts rather than the corpus contents themselves.