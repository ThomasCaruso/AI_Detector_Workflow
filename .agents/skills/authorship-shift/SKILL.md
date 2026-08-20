---
name: authorship-shift
description: Rewrite, draft, or revise prose so it is less formulaic, more natural, and structurally varied while preserving the source meaning, facts, numbers, qualifications, citations, and level of certainty. Use for polishing AI-assisted drafts, removing templated writing habits, matching a requested voice, or improving document-level flow without inventing experience or evidence.
license: MIT
compatibility: Works in OpenAI Codex and other Agent Skills-compatible clients. No local model, Python package, API key, or network access required.
metadata:
  version: "1.2.0"
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

### 3. Build from lexical anchors

Before polishing sentences, identify a few content-bearing nouns and verbs for each major idea. These should come from the subject itself rather than from generic analytical vocabulary.

Prefer sentences built around concrete actions and objects when the content supports them. For example, a rival can `ship`, a customer can `switch`, a manager can `fund` or `defer`, a process can `cut` labor hours, and an API can `retry`. Do not replace a simple word with a rarer synonym merely to create variety.

If a major sentence could be moved unchanged into many unrelated essays, silently produce at least two materially different renderings and choose the one that is more content-specific while remaining clear and faithful.

See `references/LEXICAL_RECONSTRUCTION.md` for the detailed lexical method.

### 4. Draft naturally

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
- Do not lean repeatedly on generic frames such as `X works the same way`, `X can also`, `The result can be`, `X is a useful example`, `Even with those limits`, or polished `not only X, but Y` constructions. Keep one when it is genuinely the clearest formulation; otherwise state the underlying mechanism directly.
- Keep useful repetition when terminology or reasoning requires it.
- Preserve the source's degree of confidence. Do not turn “may,” “suggests,” or “is associated with” into certainty.
- Do not fabricate anecdotes, personal experience, quotes, citations, typos, slang, or factual detail to make prose seem more human.
- Do not insert deliberate errors or awkwardness.

### 5. Run a global revision

Read the draft as a complete document rather than as isolated sentences. Fix:

- repetitive cadence;
- unnecessary restatement;
- paragraphs or sentences that perform suspiciously uniform rhetorical jobs;
- repeated transition scaffolding;
- repeated mirrored contrasts or list structures;
- abstract wrappers that could be replaced by a direct action or concrete object;
- over-explained conclusions;
- generic openings or closings;
- abrupt changes in logic;
- places where the language became more certain or less precise than the source.

Do not polish away useful irregularity that comes naturally from the content.

### 6. Run an architecture and lexical audit

Internally reduce the draft to a short sequence of rhetorical functions, for example:

`claim → reason A → reason B → reason C → caveat → thesis restatement`

If the sequence looks like a generic essay template rather than the natural shape of the subject, rebuild it.

Then scan the wording itself. Check specifically:

- Did the rewrite reuse the source opening without a substantive reason?
- Did it preserve the source sentence order too closely?
- Did every requested subpoint receive nearly equal space?
- Are transitions announcing relationships the reader can already infer?
- Are several sentences built from the same contrast, colon, or enumeration pattern?
- Which sentences rely on abstract nouns such as `pressure`, `dynamic`, `process`, `approach`, or `outcome` where the source provides a more concrete object?
- Which sentences rely on generic relationship verbs such as `create`, `drive`, `enable`, `lead to`, or `result in` where the subject provides a more exact action?
- Which phrase could be pasted into an unrelated analytical essay with almost no change?
- Does the last sentence merely restate a thesis already established?

Revise the clearest offenders. Do not introduce randomness for its own sake. Structural and lexical differences must remain clear, ordinary, and logically justified.

### 7. Run a fidelity check

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
- **deep rewrite** — reconstruct from the content lock, allowing substantial reorganization and lexical reconstruction while preserving meaning;
- **alternatives** — provide genuinely different structures, not synonym variants;
- **audit** — return the final prose plus a short fidelity report listing preserved immutable details, major structural changes, and any unresolved ambiguity.

## Boundary

This skill is for writing quality, stylistic variation, and semantic preservation. Do not claim that any text is guaranteed to receive a particular score or label from an authorship or AI-detection system, and do not optimize against a named detector. If disclosure of AI assistance is required by a school, employer, publisher, platform, or other institution, do not use this workflow to conceal that requirement.
