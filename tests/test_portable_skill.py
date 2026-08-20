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
    assert version and version.group(1) == "1.1.0"
    assert "{{" not in text and "}}" not in text


def test_deep_rewrite_requires_reconstruction_and_architecture_audit():
    text = SKILL.read_text(encoding="utf-8")
    fallback = (ROOT / "portable" / "CHATGPT_PROMPT.md").read_text(encoding="utf-8")

    required_skill_phrases = [
        "Reconstruct the document from the lock",
        "Treat the source opening as disposable",
        "Choose the support order from scratch",
        "Run an architecture audit",
        "Did it preserve the source sentence order too closely?",
    ]
    for phrase in required_skill_phrases:
        assert phrase in text

    required_fallback_phrases = [
        "Reconstruct at the document level",
        "Treat the source opening as disposable",
        "Choose the support order from scratch",
        "Architecture audit",
    ]
    for phrase in required_fallback_phrases:
        assert phrase in fallback


def test_first_eval_case_is_recorded():
    case = ROOT / "evals" / "cases" / "competition_innovation_001.md"
    assert case.exists()
    text = case.read_text(encoding="utf-8")
    assert "QuillBot AI detector" in text
    assert "Pangram" in text
    assert "descriptive test metadata only" in text
    assert "The opening was copied exactly" in text


def test_primary_readme_does_not_require_local_inference():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Primary deliverable: portable Agent Skill" in readme
    assert "does not require a local model" in readme
    assert "optional research infrastructure" in readme
