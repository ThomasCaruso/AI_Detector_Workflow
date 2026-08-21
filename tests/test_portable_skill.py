from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills" / "authorship-shift"
SKILL = SKILL_ROOT / "SKILL.md"


def _frontmatter(text: str) -> str:
    assert text.startswith("---\n")
    parts = text.split("---", 2)
    assert len(parts) == 3
    return parts[1]


def test_portable_skill_has_agent_skills_structure():
    assert SKILL.exists()
    assert (SKILL_ROOT / "references" / "WRITING_METHOD.md").exists()
    assert (SKILL_ROOT / "references" / "SELF_CHECK.md").exists()
    assert (SKILL_ROOT / "references" / "STRUCTURAL_RECONSTRUCTION.md").exists()
    assert (SKILL_ROOT / "references" / "LEXICAL_RECONSTRUCTION.md").exists()
    assert (SKILL_ROOT / "references" / "CANDIDATE_RERANKING.md").exists()
    assert (ROOT / "portable" / "CHATGPT_PROMPT.md").exists()
    assert (ROOT / "portable" / "INSTALL.md").exists()


def test_skill_frontmatter_is_portable_and_valid():
    text = SKILL.read_text(encoding="utf-8")
    fm = _frontmatter(text)

    name = re.search(r"^name:\s*([^\n]+)$", fm, re.MULTILINE)
    description = re.search(r"^description:\s*([^\n]+)$", fm, re.MULTILINE)
    compatibility = re.search(r"^compatibility:\s*([^\n]+)$", fm, re.MULTILINE)
    version = re.search(r'^\s*version:\s*"([^\n]+)"$', fm, re.MULTILINE)

    assert name and name.group(1).strip() == "authorship-shift"
    assert re.fullmatch(r"[a-z0-9-]{1,64}", name.group(1).strip())
    assert description and 1 <= len(description.group(1).strip()) <= 1024
    assert compatibility and "No local model" in compatibility.group(1)
    assert version and version.group(1) == "1.3.0"
    assert "{{" not in text and "}}" not in text


def test_v13_uses_semantic_compression_and_candidate_reranking():
    text = SKILL.read_text(encoding="utf-8")
    fallback = (ROOT / "portable" / "CHATGPT_PROMPT.md").read_text(encoding="utf-8")
    reranking = (SKILL_ROOT / "references" / "CANDIDATE_RERANKING.md").read_text(encoding="utf-8")

    required_skill_phrases = [
        "Compress the source into content atoms",
        "Use local candidate reranking",
        "at least three materially different constructions",
        "Run one restraint pass",
        "Do not keep polishing",
    ]
    for phrase in required_skill_phrases:
        assert phrase in text

    required_fallback_phrases = [
        "Compress into content atoms",
        "Use local candidate reranking",
        "at least three materially different constructions",
        "Run one restraint pass",
    ]
    for phrase in required_fallback_phrases:
        assert phrase in fallback

    required_reference_phrases = [
        "Start from content atoms",
        "Generate materially different candidates",
        "Rank for fit, not rarity",
        "Use a neighborhood check",
        "Stop after selection",
    ]
    for phrase in required_reference_phrases:
        assert phrase in reranking


def test_v13_does_not_claim_tokenizer_or_sampling_control():
    reranking = (SKILL_ROOT / "references" / "CANDIDATE_RERANKING.md").read_text(encoding="utf-8")
    assert "cannot directly change the host model's tokenizer, logits, temperature, top-p, or sampling implementation" in reranking
    assert "does not provide direct access to token probabilities" in reranking


def test_eval_cases_record_progress_and_regression():
    first = ROOT / "evals" / "cases" / "competition_innovation_001.md"
    second = ROOT / "evals" / "cases" / "competition_innovation_002.md"
    assert first.exists()
    assert second.exists()

    first_text = first.read_text(encoding="utf-8")
    second_text = second.read_text(encoding="utf-8")

    assert "AuthorshipShift v1.1 | 23% AI | 100% AI" in first_text
    assert "AuthorshipShift v1.2 | 63% AI | not run" in second_text
    assert "limited external-testing budget" in second_text
    assert "Direction for v1.3" in second_text
    assert "candidate-selection or reranking layer" in second_text


def test_primary_readme_does_not_require_local_inference():
    """The portable Skill must stay usable without local inference.

    The v0.8 two-layer rewrite changed the wording that previously carried this
    guarantee, so the assertions track the current README. The requirement is
    unchanged: the Skill is the user-facing interface, and the engine is
    research infrastructure a normal user never has to install.
    """

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "The Skill is the user-facing interface." in readme
    assert (
        "A normal end user does not need to download a local model merely to use the portable Skill."
        in readme
    )
    assert "The engine is the research and control layer." in readme
