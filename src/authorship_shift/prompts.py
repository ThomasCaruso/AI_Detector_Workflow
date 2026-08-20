from __future__ import annotations

from pathlib import Path

SKILL_ORDER = [
    "01_content_lock.md",
    "02_structure_planner.md",
    "03_draft_writer.md",
    "04_global_reviser.md",
    "05_fidelity_judge.md",
    "06_quality_judge.md",
    "07_selector.md",
    "08_operator_rewriter.md",
]


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_skill(name: str) -> str:
    return (repo_root() / "skills" / name).read_text(encoding="utf-8")


def load_operator(name: str) -> str:
    path = repo_root() / "skills" / "operators" / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Unknown composition operator: {name}")
    return path.read_text(encoding="utf-8").strip()


def render_skill(name: str, **values: str) -> str:
    text = load_skill(name)
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text
