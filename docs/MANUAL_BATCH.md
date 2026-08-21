# Zero-API Manual Candidate Batches

This workflow is for Engine v2 development when you do not want to pay for API calls or repeatedly spend external-detector credits.

It uses ChatGPT, Codex, or another model surface for generation and the local AuthorshipShift repository only for reproducible prompt preparation and candidate analysis.

## 1. Pick a seed case

The current self-contained cases are stored in:

```text
evals/engine_v2_seed_cases.json
```

They cover:

- business analysis;
- technical incident explanation;
- science-summary fidelity;
- concise professional writing;
- analytical argument.

All factual scenarios are self-contained so routine evaluation does not require web research.

## 2. Prepare an independent candidate batch

From the repository root:

```bash
python scripts/prepare_manual_batch.py competition_innovation_001
```

This creates:

```text
experiments/manual_batches/competition_innovation_001/
├── README.md
├── manifest.json
├── prompts/
│   ├── 01_direct-plain.md
│   ├── 02_mechanism-first.md
│   ├── 03_constraint-first.md
│   ├── 04_evidence-first.md
│   └── 05_compressed-asymmetric.md
└── outputs/
```

The manifest records the requested generation profile and sampling controls for each candidate.

### Replicates, and why you usually want them

The command above produces one candidate per profile. That is enough to inspect
candidates and run the batch gate, but it **cannot** tell you whether the
profiles did anything: with one sample per profile there is no within-profile
dispersion to compare against, so a profile effect is indistinguishable from
ordinary sampling noise.

For the collapse experiment, ask for at least two samples per profile:

```bash
python scripts/prepare_manual_batch.py business_valuation_001 --samples-per-profile 2
```

This writes ten prompts instead of five:

```text
prompts/01_direct-plain_c1.md
prompts/01_direct-plain_c2.md
...
prompts/05_compressed-asymmetric_c2.md
```

The two prompts for a profile are identical, and that is deliberate. Running
them as separate generations is what produces the within-profile term. Do not
shortcut this by asking one response for two variants.

Five profiles at two samples is the smallest design with enough permutation
resolution to produce a significant result; see `docs/ENGINE_V2.md`.

## 3. Generate each candidate separately

Run each prompt file as a separate generation in the model surface you are testing.

Do not paste all five profiles into one prompt and ask the model to provide five variants. The point of the harness is to preserve independent generation trajectories where the model surface allows it.

Save only the generated prose to the matching file under `outputs/`, for example:

```text
outputs/01_direct-plain.txt
outputs/02_mechanism-first.txt
outputs/03_constraint-first.txt
outputs/04_evidence-first.txt
outputs/05_compressed-asymmetric.txt
```

The portable Skill may be invoked if the experiment is specifically testing the Skill + engine combination. If the experiment is testing the underlying generator alone, omit the Skill and record that choice in the experiment notes.

## 4. Analyze without external services

When all outputs are present:

```bash
python scripts/analyze_manual_batch.py experiments/manual_batches/competition_innovation_001
```

The command writes:

```text
experiments/manual_batches/competition_innovation_001/analysis.json
```

The report includes deterministic diagnostics for each candidate:

- pairwise candidate distance and nearest-neighbor distance;
- source trigram overlap;
- structural distance;
- sentence-opening repetition and entropy;
- transition frequency;
- repeated trigrams;
- conservative immutable-detail coverage and the number of checkable details;
- basic length and lexical metrics.

It also reports, for the batch as a whole:

- `fidelity_evidence` — whether the immutable-detail precheck actually had
  anything to verify, so a coverage of `1.0` on a source with no numbers or
  names is never mistaken for verified fidelity;
- the **collapse analysis** — between-profile versus within-profile dispersion
  with a permutation test, when replicates are available;
- a **shortlist** — candidates ranked by accumulated defects, with a
  diversity-aware selection among quality-equivalent candidates.

These diagnostics do not identify human or AI authorship. They exist to catch engineering failures such as near-duplicate candidate batches, excessive source copying, lost numbers, or profile collapse.

Shortlist size is configurable:

```bash
python scripts/analyze_manual_batch.py experiments/manual_batches/business_valuation_001 --select 3
```

## 5. Analyze a historical structured case

The competition/innovation Skill experiment is already stored as:

```text
evals/data/competition_innovation_001.json
```

Analyze it directly:

```bash
python scripts/analyze_candidate_set.py evals/data/competition_innovation_001.json
```

For JSON output:

```bash
python scripts/analyze_candidate_set.py evals/data/competition_innovation_001.json --json
```

## 6. When to use scarce external validation

Do not automatically send every candidate to a paid or rate-limited external system.

A better checkpoint rule is:

1. candidate batch is meaningfully diverse;
2. fidelity checks pass;
3. writing quality is at least as strong as the baseline;
4. the change represents a new generation strategy rather than another wording tweak;
5. only then record scarce external observations if they are still useful to the research question.

External labels should remain metadata, not the engine's optimization objective.
