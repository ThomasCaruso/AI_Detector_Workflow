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

Decision-grade preparation requires at least **three approved source documents per
target genre** so every genre can have a source-level train, dev, and holdout cell.
For the intended 30-50 document bootstrap, aim for roughly 6-10 independently
sourced documents per genre rather than relying on the three-document minimum.

See `SOURCE_POOLS.md` for bootstrap source pools and their rights-policy links.

## 2. Create raw excerpt JSONL locally

Raw text is gitignored. One line per excerpt:

```json
{"id":"usgs-001-p12-a","source_id":"usgs-001","genre":"science_summary","instruction":"Summarize the finding in plain analytical prose.","target_text":"<human prose>","excerpt_locator":"p. 12, paragraphs 2-3","metadata":{}}
```

Rules:

- `target_text` is copied exactly from the approved human source except for
  mechanical whitespace normalization;
- do not improve, simplify, paraphrase, or clean its style;
- keep enough surrounding context in `excerpt_locator` to audit the excerpt;
- exclude quotations or sections written by a different authorial voice unless
  that voice is intentionally registered as its own source, even when rights are
  otherwise clean;
- exclude tables, captions, boilerplate, references, navigation text, and image
  descriptions;
- prefer sustained prose of roughly 80-500 words for the first corpus.

Before committing a source slot, test excerpt viability. A rights-clean document
that yields only one short usable paragraph may be a poor corpus source even if its
provenance is excellent. For the first pilot, prefer documents that can supply
roughly 3-5 independent sustained-prose excerpts without dipping into bullets,
appendices with different authorship, captions, or repeated boilerplate.

## 3. Freeze genre-stratified source splits and prepare annotation packets

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

Annotation preparation copies each source snapshot into packet metadata **before**
the frozen annotation manifest is written. Changing the target, provenance, split,
or source artifact hash afterward invalidates the frozen contract.

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

## 4. Semantic-plan annotation

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

## 5. Compile and validate

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

## 6. Audit the corpus

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

## 7. Validate without training

```bash
python scripts/validate_lora_dataset.py research/lora/datasets/lora_v1.jsonl
python research/lora/train_qlora.py research/lora/datasets/lora_v1.jsonl
```

The dry run reports genre x split coverage but remains diagnostic: it does not
require a complete corpus and still performs no model download or heavy import.
`--execute` is stricter and refuses training unless the full five-genre split
contract is satisfied.

## Initial corpus target

Do not optimize for a large number of excerpts immediately. First build a small,
auditable corpus that can exercise the entire pipeline:

```text
~30-50 source documents
~150-300 excerpts
5 target genres
~6-10 source documents per genre
multiple provenance/source pools
train/dev/holdout represented inside every genre
```

This is enough for a first *pipeline and overfit-risk experiment*, not enough to
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
