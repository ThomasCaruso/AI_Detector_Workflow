# AuthorshipShift

A portable writing workflow for rewriting or drafting prose with stronger document-level structure, less formulaic language, and strict semantic fidelity.

**The primary version does not require a local model, Ollama, Python, or an API key.** ChatGPT, Codex, or another Agent Skills-compatible host provides the model; AuthorshipShift provides the reusable writing method.

## Primary deliverable: portable Agent Skill

The installable skill lives at:

```text
.agents/skills/authorship-shift/
├── SKILL.md
└── references/
    ├── SELF_CHECK.md
    └── WRITING_METHOD.md
```

The skill follows the Agent Skills open format. It converts the original multi-stage pipeline into one host-model workflow:

```text
source / notes
    ↓
silent semantic lock
    ↓
document-level structure choice
    ↓
full draft or rewrite
    ↓
global revision
    ↓
fidelity check
    ↓
finished prose
```

No external model process is needed.

### Codex

Open this repository in Codex, or copy `.agents/skills/authorship-shift/` into the `.agents/skills/` directory of another project.

Example:

```text
Use AuthorshipShift to deeply rewrite this draft while preserving every factual claim, number, qualification, citation, and causal relationship. Return only the finished prose.
```

### ChatGPT

If your ChatGPT surface supports personal Skill uploads, zip the `authorship-shift` directory and upload it as a Skill.

If Skill upload is not available, use the single-file fallback:

```text
portable/CHATGPT_PROMPT.md
```

Attach it to a conversation or paste its contents, then provide the writing task.

See [`portable/INSTALL.md`](portable/INSTALL.md) for the exact layout and usage.

## What the writing method preserves

Before changing prose, the skill silently locks:

- required factual and argumentative claims;
- names, dates, figures, units, quotations, citations, and technical terms;
- causal direction and comparisons;
- qualifications, caveats, and uncertainty;
- conclusions and recommendations;
- unsupported inferences that must not be introduced.

The rewrite can substantially change information order, paragraph function, sentence shape, emphasis, compression, and transitions while those protected elements remain fixed.

## What it changes

The skill works at the document level rather than performing synonym replacement. Depending on the material it can use structures such as:

- claim first;
- mechanism first;
- evidence then judgment;
- contrast driven;
- chronological or causal progression;
- compressed reasoning;
- asymmetric emphasis.

It also removes common template-level problems such as repetitive cadence, generic openings, empty signposting, unnecessary restatement, over-balanced lists, and paragraphs that all perform the same rhetorical function.

It does **not** create naturalness by adding fake anecdotes, deliberate mistakes, invented personal experience, fabricated citations, or random slang.

## Voice matching

When the user supplies genuine writing samples or explicit style preferences, AuthorshipShift treats those as the strongest style signal. It can match observable features such as directness, density, vocabulary level, contractions, fragments, humor, formality, and paragraph shape without inventing biographical details or opinions.

## Research harness (optional)

The repository also contains the earlier Python research harness for controlled experiments, ablations, provenance, holdout validation, and compute accounting.

That harness is now **optional research infrastructure**, not the way a normal user runs AuthorshipShift. It remains useful for studying whether structural transformations preserve meaning and writing quality, but it is not required to install or use the writing skill.

Research documentation remains under `docs/`, including:

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/RESEARCH_PROTOCOL.md`](docs/RESEARCH_PROTOCOL.md)
- [`docs/ABLATIONS.md`](docs/ABLATIONS.md)
- [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md)
- [`docs/HOLDOUT_PROTOCOL.md`](docs/HOLDOUT_PROTOCOL.md)

For the optional Python harness, see the historical CLI and configuration under `src/`, `configs/`, and `tests/`.

## Scope

AuthorshipShift is for writing quality, structural variation, semantic preservation, and research into text transformation. It does not guarantee a particular result from any AI-writing or authorship detector and should not be used to conceal AI assistance where disclosure is required by a school, employer, publisher, platform, or other institution.

## License

MIT.
