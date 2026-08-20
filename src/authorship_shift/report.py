from __future__ import annotations

from pathlib import Path
from typing import Any

from .diversity import summarize_diversity
from .models import read_json


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def build_markdown_report(experiment_root: str | Path) -> str:
    root = Path(experiment_root)
    manifest = read_json(root / "manifest.json")
    config = read_json(root / "config.json")
    candidates = []
    for cid in manifest.get("candidate_ids", []):
        path = root / "candidates" / f"{cid}.json"
        if path.exists():
            candidates.append(read_json(path))

    external_results = []
    ext_dir = root / "external"
    if ext_dir.exists():
        for path in sorted(ext_dir.glob("*.json")):
            external_results.append(read_json(path))

    selection = {}
    if (root / "selection.json").exists():
        selection = read_json(root / "selection.json")

    diversity = summarize_diversity([c.get("text", "") for c in candidates])
    stage_counts: dict[str, int] = {}
    for c in candidates:
        stage = c.get("stage", "unknown")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    lines = [
        f"# Experiment Report — {manifest.get('title', root.name)}",
        "",
        "## Summary",
        "",
        f"- Candidates: **{len(candidates)}**",
        f"- External detector queries used: **{manifest.get('external_queries_used', 0)} / {config.get('external_evaluation', {}).get('milestone_queries_budget', 0)}**",
        f"- Frozen candidates: **{len(manifest.get('frozen_candidate_ids', []))}**",
        f"- Mean pairwise candidate distance: **{diversity.mean_pair_distance:.3f}**",
        "",
        "## Candidate stages",
        "",
    ]
    for stage, count in sorted(stage_counts.items()):
        lines.append(f"- {stage}: {count}")

    lines.extend(["", "## Candidate table", "", "| ID | Stage | Model | Fidelity | Quality Δ | Frozen |", "|---|---|---|---:|---:|---|"])
    for c in candidates:
        md = c.get("metadata", {}) or {}
        fidelity = (md.get("fidelity") or {}).get("score", "")
        quality = (md.get("quality") or {}).get("candidate_minus_source", "")
        model = md.get("generator_model") or md.get("reviser_model") or ""
        frozen = "yes" if md.get("frozen_at") else ""
        lines.append(f"| `{c.get('id')}` | {c.get('stage')} | {model} | {_fmt(fidelity)} | {_fmt(quality)} | {frozen} |")

    lines.extend(["", "## Selected candidates", ""])
    recommended = selection.get("recommended_candidate_ids", []) if isinstance(selection, dict) else []
    if recommended:
        for cid in recommended:
            lines.append(f"- `{cid}`")
    else:
        lines.append("No selection has been recorded yet.")

    lines.extend(["", "## External evaluations", ""])
    if external_results:
        lines.extend(["| Detector | Candidate | Label | Score | Frozen before test |", "|---|---|---|---:|---|"])
        for r in external_results:
            lines.append(
                f"| {r.get('detector', '')} | `{r.get('candidate_id') or ''}` | {r.get('label', '')} | {_fmt(r.get('score', ''))} | {r.get('frozen_before_test', '')} |"
            )
    else:
        lines.append("No external detector results recorded. This is expected during development.")

    lines.extend([
        "",
        "## Interpretation",
        "",
        "Local metrics and candidate diversity are development diagnostics only. They are not presented as a surrogate for Pangram or any other proprietary detector. External detector results should be treated as sparse held-out evaluations.",
        "",
    ])
    return "\n".join(lines)


def write_report(experiment_root: str | Path, output: str | Path | None = None) -> Path:
    root = Path(experiment_root)
    out = Path(output) if output else root / "report.md"
    out.write_text(build_markdown_report(root), encoding="utf-8")
    return out
