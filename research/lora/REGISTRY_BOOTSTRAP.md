# Bootstrap the first 30-document registry

Start with six candidate document slots in each of the five target genres. This is a planning scaffold only; it is not training data and it contains no approved provenance.

## 1. Create the local registry

```bash
python scripts/init_lora_registry.py \
  research/lora/local_corpus/source_registry.json
```

The generated file contains 30 records:

```text
business_analysis       6
technical_explanation   6
science_summary         6
professional_writing    6
analytical_argument     6
```

Every record begins as `status: candidate`. The placeholder `provenance_kind` is provisional and must be verified or replaced during document-level rights review.

The generated `source_id` values are also placeholders. When a slot gets an exact document, replace the slot ID with a stable document-specific ID. Do not swap a different document behind an existing final `source_id`; the split contract uses document identity through that ID.

## 2. Preview the split matrix before approval

```bash
python scripts/plan_lora_splits.py \
  research/lora/local_corpus/source_registry.json \
  --include-candidates \
  --json-out research/lora/local_corpus/split_preview.json
```

For the untouched 6-per-genre scaffold, every target genre should preview as:

```text
train=4 dev=1 holdout=1
```

`--include-candidates` is planning-only. The script creates an in-memory copy in which candidate records are temporarily eligible for split calculation. It does not change the registry file, approve a source, create annotation packets, or make a source trainable.

A candidate preview writes `preview_split_sha256`, not `registry_split_sha256`. Treat it as a planning fingerprint only.

## 3. Replace slots with exact candidate documents

For each slot, fill:

- a stable document-specific `source_id`;
- exact title;
- one target genre;
- canonical URL or stable local locator;
- author/agency;
- candidate provenance kind;
- license/public-domain status where applicable;
- document locator such as report number, DOI, page range, or file identifier;
- notes about third-party material or sections to exclude.

Keep `status: candidate` during this stage.

After each meaningful registry change, rerun the candidate preview. A document replacement should normally change the preview fingerprint because the stable document-specific `source_id` changes.

## 4. Review rights at the document level

Only change a source to `status: approved` after the exact document has been reviewed. Agency-level policy is evidence, not blanket approval for every paragraph hosted by that agency.

For externally sourced public-domain/licensed documents, approval requires the fields enforced by `corpus_pipeline.py`, including the canonical URL and applicable license/public-domain label.

Quoted third-party passages, contractor-authored sections, figures, tables, photographs, and reproduced material require separate attention. Exclude material whose rights basis is unclear.

## 5. Freeze the approved split contract

Once all intended documents are reviewed and approved, run the planner **without** candidate preview:

```bash
python scripts/plan_lora_splits.py \
  research/lora/local_corpus/source_registry.json \
  --json-out research/lora/local_corpus/split_plan.json
```

This is the decision-grade plan. It emits `registry_split_sha256` and requires at least three approved source documents in every target genre.

Do not start excerpt collection/annotation against a candidate preview. Begin annotation only after the approved registry and its split fingerprint are stable.

## 6. Then collect excerpts

Once the approved split contract is frozen, proceed with `CORPUS_PIPELINE.md`:

```bash
python scripts/prepare_lora_annotations.py \
  research/lora/local_corpus/raw_excerpts.jsonl \
  research/lora/local_corpus/source_registry.json \
  research/lora/annotations
```

Annotation preparation recomputes the registry-derived split assignment; it does not trust the preview file.
