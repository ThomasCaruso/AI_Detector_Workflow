---
name: authorship-shift
description: Rewrite, draft, or revise prose so it is less formulaic, more natural, and structurally varied while preserving the source meaning, facts, numbers, qualifications, citations, and level of certainty. Use for polishing AI-assisted drafts, removing templated writing habits, matching a requested voice, or improving document-level flow without inventing experience or evidence.
license: MIT
compatibility: Works in OpenAI Codex and other Agent Skills-compatible clients. No local model, Python package, API key, or network access required.
metadata:
  version: "1.3.0"
  project: "AuthorshipShift"
---

# AuthorshipShift

Use the host model itself. Do not call a local model or require Ollama.

## Default behavior

Return finished prose only unless the user asks for analysis, alternatives, or an audit.

The goal is not to decorate a draft. Rebuild the writing from its meaning while preserving every required fact, relationship, qualification, and constraint.

## Workflow

### 1. Build a silent semantic lock

Internally capture:

- purpose and audience;
- required claims;
- exact names, dates, figures, quotations, citations, technical terms, and other immutable details;
- causal relationships and comparisons;
- caveats, uncertainty, and level of certainty;
- required conclusions or recommendations;
- anything that must not be invented.

### 2. Compress the source into content atoms

Before drafting, reduce the material internally to terse fragments rather than polished sentences. Keep meaning, not wording.

Example shape:

`customers can switch / rival ships better product / margin pressure / uncertain R&D becomes rational / bottlenecks become urgent / short-term competition can damage basic research`

Do not preserve the source opening, sentence sequence, transition language, or clause structure unless one of those is genuinely required.

This semantic-compression step is mandatory for deep rewrites and new drafts from highly structured prompts.

### 3. Choose the document shape from the atoms

Decide what deserves emphasis and in what order. Do not automatically use thesis → reason 1 → reason 2 → reason 3 → counterpoint → balanced conclusion.

A strong shape may begin with a mechanism, concrete consequence, tension, example, or claim. Preserve every requested point, but do not allocate equal space merely because the prompt lists points evenly.

### 4. Use local candidate reranking

For each major sentence or sentence cluster, silently consider at least three materially different constructions before committing.

The candidates must differ in more than synonyms. Change at least two of:

- grammatical subject;
- main verb;
- information order;
- clause structure;
- level of abstraction;
- whether a transition is needed;
- whether two related ideas belong in one sentence or separate sentences.

Choose the candidate that is clearest, most specific to the actual subject, least dependent on generic analytical scaffolding, and least repetitive relative to nearby sentences.

Do not choose obscure vocabulary merely because it is less common.

See `references/CANDIDATE_RERANKING.md` for the detailed method.

### 5. Draft in a stable voice

If the user provides writing samples, use them as the strongest style signal. Match observable features such as directness, density, sentence shape, vocabulary, contractions, fragments, humor, formality, and paragraph shape.

Without a voice sample, default to plain, specific prose rather than generic school-essay exposition. Let the subject supply the nouns and verbs.

Do not fabricate anecdotes, personal experience, quotes, citations, slang, errors, or biographical detail.

### 6. Run one restraint pass

Read the piece once as a whole. Revise only clear problems:

- repeated sentence openings or grammatical shapes;
- unnecessary transition scaffolding;
- a copied or generic opening;
- repeated abstract wrappers where a concrete action is available;
- mechanically balanced lists or contrasts;
- a conclusion that simply restates the thesis;
- accidental changes in certainty or causality.

Do not keep polishing after the prose is clear and faithful. Excessive cleanup can make every sentence equally smooth and restore the template the rewrite was meant to remove.

### 7. Fidelity check

Compare the final draft against the semantic lock. It must preserve:

- all required claims;
- all immutable details;
- all important qualifications;
- causal direction;
- comparisons and numerical relationships;
- source attribution and citations;
- the original level of certainty.

Reject any revision that adds unsupported claims, loses a required fact, changes a number or name, reverses causality, or turns uncertainty into certainty.

Use `references/SELF_CHECK.md` for information-dense or high-stakes text.

## Output modes

- **rewrite / polish / make natural** — one finished version;
- **light edit** — preserve structure and voice closely;
- **deep rewrite** — semantic compression + reconstruction + candidate reranking;
- **voice match** — use supplied writing samples as the primary style prior;
- **alternatives** — produce genuinely different document shapes;
- **audit** — prose plus a concise fidelity report.

## Boundary

This skill is for writing quality, specificity, voice, structural variation, and semantic preservation. Do not claim or promise a particular result from an authorship or AI-detection system, and do not optimize against a named detector. If disclosure of AI assistance is required by a school, employer, publisher, platform, or other institution, do not use this workflow to conceal that requirement.
