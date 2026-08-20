# Install AuthorshipShift without a local model

AuthorshipShift's primary deliverable is the Agent Skill under:

```text
.agents/skills/authorship-shift/
```

It does not require Python, Ollama, a local LLM, or an API key. The model already running in the host product performs the workflow.

## Codex

Keep the repository as a project and open it in Codex, or copy this directory into another project:

```text
.agents/skills/authorship-shift/
```

The folder contains the required `SKILL.md` plus reference material. Skills-compatible agents discover the skill from its metadata and load the full instructions when a writing task matches.

Example request:

```text
Use AuthorshipShift to deeply rewrite this draft while preserving every factual claim, number, qualification, and citation. Return only the finished prose.
```

## ChatGPT with Skills upload available

Package the `authorship-shift` directory as a zip and upload it as a Skill. The zip root should contain `SKILL.md`, with the `references/` directory beside it.

Expected bundle:

```text
authorship-shift/
├── SKILL.md
└── references/
    ├── SELF_CHECK.md
    └── WRITING_METHOD.md
```

## Ordinary ChatGPT fallback

If the account or surface does not expose personal Skill uploading, use:

```text
portable/CHATGPT_PROMPT.md
```

Attach that Markdown file to the conversation (or paste its contents), then provide the text you want drafted or rewritten. The fallback contains the same core workflow in a single file.

Example:

```text
Follow the attached AuthorshipShift instructions. Deeply rewrite the draft below. Preserve the meaning, figures, causal relationships, and uncertainty. Return only the final prose.

[paste draft]
```

## What the skill does

The host model performs five internal stages in one invocation:

1. silent semantic/content lock;
2. document-level structural choice;
3. full rewrite or draft;
4. global revision for repetitive or templated patterns;
5. fidelity check against the source.

The user receives the final prose unless an audit or alternatives were requested.

## Research harness

The older Python/Ollama pipeline remains in the repository as an optional research and evaluation harness. It is not required to use the portable writing skill.
