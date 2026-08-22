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
- observed artifact locator such as exact PDF URL/filename, report number, DOI, or local file identifier;
- notes about third-party material, distinct authorial voices, or sections to exclude.

Keep `status: candidate` during this stage.

Before spending annotation effort, inspect the exact artifact for **excerpt viability**. Passage yield is empirical rather than fixed. The first frozen CBO business source yielded at least 11 clean 80-500-word blocks, so the earlier 3-5-per-document assumption is retired.

The first adapter pilot instead uses two asymmetric per-genre constraints:

- **hard structural floor:** at least 6 independent approved documents;
- **provisional volume target:** at least 25 clean passages.

High passage yield never substitutes for independent documents. The volume target may be revised after multiple source pools and genres are audited.

Rights-clean and style-clean are separate checks. Reproduced agency comment letters, contractor appendices, quotations, or other sections written in a different voice should not be absorbed into the host document's style corpus merely because their rights are clear.

After each meaningful registry change, rerun the candidate preview. A document replacement should normally change the preview fingerprint because the stable document-specific `source_id` changes.

## 4. Review rights and freeze the exact artifact

Agency-level policy is evidence, not blanket approval for every paragraph hosted by that agency. Review the exact document and the sections intended for the corpus.

Every eventual approved source requires an exact-artifact snapshot. Download or otherwise freeze the file actually reviewed, then hash it locally:

```bash
python scripts/hash_source_artifact.py \
  research/lora/local_corpus/artifacts/example.pdf \
  --artifact-kind pdf \
  --revision-label "optional published revision label"
```

Copy the resulting `retrieved_at`, `sha256`, `artifact_kind`, and `revision_label` into the registry's `source_snapshot`. This applies to all approved sources, including user-owned and consented material: source ownership does not prevent a local file from changing.

For externally sourced public-domain/licensed documents, approval still separately requires the canonical URL and applicable license/public-domain label.

Quoted third-party passages, contractor-authored sections, figures, tables, photographs, and reproduced material require separate attention. Exclude material whose rights basis or authorship suitability is unclear.

## 5. Freeze canonical text for PDFs

A PDF hash pins bytes, not extracted prose. Before a PDF can enter the decision-grade approved split plan, create the canonical text derivation described in `CORPUS_PIPELINE.md`.

Install the pinned extractor:

```bash
pip install -r research/lora/extraction-requirements.txt
```

Extract the exact frozen artifact:

```bash
python scripts/extract_source_text.py \
  research/lora/local_corpus/artifacts/example.pdf \
  research/lora/local_corpus/extracted/example.canonical.json \
  --source-id example-source-id
```

Inspect extraction artifacts. Safe source-agnostic normalization is automatic, but ambiguous de-hyphenation or intra-word-space repair must be recorded in a reviewed correction ledger. Use:

```bash
python scripts/init_text_corrections.py \
  research/lora/local_corpus/extracted/example.canonical.json \
  research/lora/local_corpus/extracted/example.corrections.json
```

After adding reviewed page-scoped replacements, rerun `extract_source_text.py --corrections ...` and populate `source_text_derivation` in the local registry with the resulting extractor/version, base-text hash, correction hash, canonical-text hash, and registry-relative canonical-text path.

The canonical extraction and correction files stay gitignored. Their hashes become the reviewable contract.

## 6. Approve and freeze the decision-grade split contract

Only change a source to `status: approved` after its rights/authorship review, exact-artifact snapshot, and—when the artifact is a PDF—canonical text derivation are complete.

Once the intended sources meet those conditions, run the planner **without** candidate preview:

```bash
python scripts/plan_lora_splits.py \
  research/lora/local_corpus/source_registry.json \
  --json-out research/lora/local_corpus/split_plan.json
```

Candidate preview is intentionally permissive. Approved-only planning is not: it validates exact source snapshots and requires a locally verifiable canonical text derivation for every approved PDF before issuing the real split fingerprint.

The splitter's code-level minimum is three approved source documents in every target genre. The first real adapter pilot imposes the stricter research floor of six independent approved documents per genre.

The plan emits independent artifact and split evidence:

- `registry_split_sha256` — exact document identities and split assignments;
- `source_snapshot_set_sha256` — exact reviewed artifact versions.

Changing a document version while retaining the same `source_id` changes the source-snapshot fingerprint even if the split assignment remains identical. Changing the PDF extraction/correction contract prevents decision-grade planning or annotation until the registry and local canonical text agree again.

Do not start excerpt annotation against a candidate preview. Begin annotation only after the approved registry, split fingerprint, source snapshot fingerprint, and PDF canonical-text derivations are stable.

## 7. Then collect excerpts

Once the approved contracts are frozen, proceed with `CORPUS_PIPELINE.md`:

```bash
python scripts/prepare_lora_annotations.py \
  research/lora/local_corpus/raw_excerpts.jsonl \
  research/lora/local_corpus/source_registry.json \
  research/lora/annotations
```

For PDF sources, raw `target_text` must come from canonical text. Annotation preparation permits whitespace-only reflow but rejects character-level edits that are absent from the reviewed correction ledger. It copies both the source snapshot and text-derivation contract into packet metadata and freezes them alongside target/provenance fields.
