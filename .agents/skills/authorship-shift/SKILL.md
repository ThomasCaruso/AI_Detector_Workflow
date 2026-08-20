---
name: authorship-shift
description: Rewrite, draft, or revise prose so it is less formulaic, more natural, and structurally varied while preserving the source meaning, facts, numbers, qualifications, citations, and level of certainty. Use for polishing AI-assisted drafts, removing templated writing habits, matching a requested voice, or improving document-level flow without inventing experience or evidence.
license: MIT
compatibility: Works in OpenAI Codex and other Agent Skills-compatible clients. No local model, Python package, API key, or network access required.
metadata:
  version: "1.1.0"
  project: "AuthorshipShift"
---

# AuthorshipShift

Use the host model itself to perform the entire workflow. Do not call a local model or require Ollama.

## Default behavior

When the user supplies prose to rewrite, return the finished prose only unless they ask for analysis, alternatives, or an audit.

When the user asks for a new draft from notes, requirements, or source material, preserve all supplied constraints and produce the finished draft directly.

## Workflow

### 1. Build a silent content lock

Before rewriting, identify internally:

- the purpose and intended audience;
- every required factual or argumentative claim;
- exact names, dates, figures, quoted language, citations, technical terms, and other immutable details;
- causal relationships and comparisons;
- qualifications, caveats, uncertainty, and epistemic strength;
- conclusions and recommendations;
- facts or implications that must not be invented.

Do not expose this lock unless the user asks for an audit.

### 2. Reconstruct the document from the lock

Do not perform sentence-by-sentence synonym replacement. In deep-rewrite mode, stop following the source sentence order once the content lock is complete. Draft from the locked ideas and the logic of the subject instead.

Treat the source opening as disposable unless it contains immutable language or is genuinely the strongest entry point. Reconsider where the piece should begin: the central implication, a concrete mechanism, a constraint, a contrast, or the main claim.

Choose the support order from scratch. Useful structures include:

- claim first;
- mechanism first;
- evidence then judgment;
- contrast driven;
- consequence then explanation;
- compressed reasoning;
- asymmetric structure;
- chronological or causal progression when the source requires it.

Preserve every required point, but do not give each point equal space simply because it appears in the prompt. Let the most consequential or difficult idea carry more weight and compress secondary points when clarity allows.

The structure should emerge from the subject, not from a fixed template. Vary where explanation, qualification, example, and conclusion appear when doing so improves the piece.

See `references/WRITING_METHOD.md` for the general method and `references/STRUCTURAL_RECONSTRUCTION.md` when a rewrite remains polished but overly orderly.

### 3. Draft naturally

Apply these rules:

- Prefer specific nouns and verbs over vague abstraction.
- Let sentence length follow the thought rather than forcing artificial variation.
- Let paragraph length follow paragraph function.
- Remove empty signposting and repeated summaries.
- Avoid mechanical three-part lists unless the content genuinely has three parts.
- Avoid inflated vocabulary when a simpler word is more exact.
- Do not force every paragraph into topic sentence → explanation → mini-conclusion.
- Do not require every sentence to perform exactly one rhetorical job. Combine evidence, judgment, mechanism, or qualification when they naturally belong together.
- Use transitions only when the logical relationship is not already clear from adjacency.
- Keep useful repetition when terminology or reasoning requires it.
- Preserve the source's degree of confidence. Do not turn “may,” “suggests,” or “is associated with” into certainty.
- Do not fabricate anecdotes, personal experience, quotes, citations, typos, slang, or factual detail to make prose seem more human.
- Do not insert deliberate errors or awkwardness.

### 4. Run a global revision

Read the draft as a complete document rather than as isolated sentences. Fix:

- repetitive cadence;
- unnecessary restatement;
- paragraphs or sentences that perform suspiciously uniform rhetorical jobs;
- repeated transition scaffolding;
- repeated mirrored contrasts or list structures;
- over-explained conclusions;
- generic openings or closings;
- abrupt changes in logic;
- places where the language became more certain or less precise than the source.

Do not polish away useful irregularity that comes naturally from the content.

### 5. Run an architecture audit

Internally reduce the draft to a short sequence of rhetorical functions, for example:

`claim → reason A → reason B → reason C → caveat → thesis restatement`

If the sequence looks like a generic essay template rather than the natural shape of the subject, rebuild it.

Check specifically:

- Did the rewrite reuse the source opening without a substantive reason?
- Did it preserve the source sentence order too closely?
- Did every requested subpoint receive nearly equal space?
- Are transitions announcing relationships the reader can already infer?
- Are several sentences built from the same contrast, colon, or enumeration pattern?
- Does the last sentence merely restate a thesis already established?

Do not introduce randomness for its own sake. Structural differences must remain clear and logically justified.

### 6. Run a fidelity check

Before returning the result, compare it against the silent content lock.

The final version must preserve:

- all required claims;
- all immutable details;
- all important qualifications;
- causal direction;
- comparisons and numerical relationships;
- source attribution and citations;
- the original level of certainty.

Reject any revision that adds unsupported claims, loses a required fact, changes a number, reverses causality, or weakens an important qualification.

Use `references/SELF_CHECK.md` when the text is information-dense or high stakes.

## User voice

If the user provides examples of their own writing or explicit style preferences, treat those as the strongest style signal. Match observable features such as directness, density, sentence shape, vocabulary level, humor, formality, and use of fragments without copying distinctive phrases unnecessarily.

Never invent biographical experience or opinions and attribute them to the user.

## Output modes

If the user asks for:

- **rewrite / polish / make natural** — return one finished version;
- **light edit** — preserve structure and voice more closely;
- **deep rewrite** — reconstruct from the content lock, allowing substantial reorganization while preserving meaning;
- **alternatives** — provide genuinely different structures, not synonym variants;
- **audit** — return the final prose plus a short fidelity report listing preserved immutable details, major structural changes, and any unresolved ambiguity.

## Boundary

This skill is for writing quality, stylistic variation, and semantic preservation. Do not claim that any text is guaranteed to receive a particular score or label from an authorship or AI-detection system, and do not optimize against a named detector. If disclosure of AI assistance is required by a school, employer, publisher, platform, or other institution, do not use this workflow to conceal that requirement.
