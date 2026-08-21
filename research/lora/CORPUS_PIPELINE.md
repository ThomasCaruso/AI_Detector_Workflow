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
- exclude quotations written by a third party unless that quoted text has its own
  independently valid provenance;
- exclude tables, captions, boilerplate, references, and navigation text;
- prefer sustained prose of roughly 80-500 words for the first corpus.

## 3. Freeze source-level splits and prepare annotation packets

```bash
python scripts/prepare_lora_annotations.py \
  research/lora/local_corpus/raw_excerpts.jsonl \
  research/lora/local_corpus/source_registry.json \
  research/lora/annotations
```

Split assignment is a deterministic hash of the frozen split seed and `source_id`.
Every excerpt from the same document therefore lands in the same split before any
semantic annotation or model evaluation occurs.

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

The second form refuses to produce a trainable corpus unless train, dev, and
holdout all contain at least one ready example. The QLoRA runner independently
rechecks the same requirement at `--execute` time.

## 6. Audit the corpus

```bash
python scripts/audit_lora_dataset.py \
  research/lora/datasets/lora_v1.jsonl \
  --json-out research/lora/local_corpus/corpus_audit.json
```

The audit reports:

- examples and words by genre;
- examples and words by provenance kind;
- examples and words by source document;
- largest source-document share;
- near-duplicate target prose using word 5-gram Jaccard similarity;
- near-duplicates that cross train/dev/holdout boundaries.

Defaults warn when one source exceeds 15% of examples or words and when a genre
has fewer than five examples. Those are corpus-design warnings rather than model
hyperparameters; tune them only with an explicit corpus rationale.

## 7. Validate without training

```bash
python scripts/validate_lora_dataset.py research/lora/datasets/lora_v1.jsonl
python research/lora/train_qlora.py research/lora/datasets/lora_v1.jsonl
```

The training runner remains dry-run by default. No model download, Torch import,
or GPU use occurs without `--execute`.

## Initial corpus target

Do not optimize for a large number of excerpts immediately. First build a small,
auditable corpus that can exercise the entire pipeline:

```text
~30-50 source documents
~150-300 excerpts
5 target genres
multiple provenance/source pools
non-empty train/dev/holdout by source document
```

This is enough for a first *pipeline and overfit-risk experiment*, not enough to
claim a production-quality writing adapter. The first training question is simply
whether the adapter moves held-out style behavior while the fidelity gates remain
clean.

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
