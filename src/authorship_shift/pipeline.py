from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .claim_diff import claim_coverage_report
from .diversity import pair_distance, summarize_diversity
from .experiment import Experiment
from .models import Candidate, write_json
from .metrics import measure, structural_distance
from .prompts import render_skill, load_operator
from .providers.base import Provider


@dataclass
class PipelineResult:
    content_lock: dict[str, Any]
    plans: list[dict[str, Any]]
    candidates: list[Candidate]
    ranking: list[dict[str, Any]]
    beam_ids: list[str]


def _json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Expected JSON from provider, got:\n{text[:1000]}") from exc


def _ranking_row(candidate: Candidate) -> dict[str, Any]:
    md = candidate.metadata
    return {
        "candidate_id": candidate.id,
        "stage": candidate.stage,
        "parent_id": candidate.parent_id,
        "generator_model": md.get("generator_model"),
        "reviser_model": md.get("reviser_model"),
        "operator": md.get("operator"),
        "fidelity": md.get("fidelity", {}),
        "quality": md.get("quality", {}),
        "claim_precheck": md.get("claim_precheck", {}),
        "structural_distance": md.get(
            "structural_distance_from_source",
            md.get("structural_distance_from_parent", 0.0),
        ),
    }


def _judge_candidate(
    exp: Experiment,
    candidate: Candidate,
    *,
    source: str,
    content_lock: dict[str, Any],
    judge_provider: Provider,
) -> dict[str, Any]:
    candidate.metadata["metrics"] = measure(candidate.text).to_dict()
    candidate.metadata["claim_precheck"] = claim_coverage_report(content_lock, candidate.text).to_dict()

    fidelity_prompt = render_skill(
        "05_fidelity_judge.md",
        SOURCE=source,
        CONTENT_LOCK=json.dumps(content_lock, indent=2),
        CANDIDATE=candidate.text,
    )
    candidate.metadata["fidelity"] = _json(judge_provider.chat(fidelity_prompt, json_mode=True))

    quality_prompt = render_skill(
        "06_quality_judge.md",
        SOURCE=source,
        CANDIDATE=candidate.text,
    )
    candidate.metadata["quality"] = _json(judge_provider.chat(quality_prompt, json_mode=True))
    candidate.metadata["judge_model"] = judge_provider.identity
    exp.add_candidate(candidate)
    return _ranking_row(candidate)


def _passes(row: dict[str, Any], gates: dict[str, Any]) -> bool:
    fidelity = row.get("fidelity", {}) or {}
    quality = row.get("quality", {}) or {}
    precheck = row.get("claim_precheck", {}) or {}
    min_fidelity = float(gates.get("minimum_fidelity", 0.96))
    min_quality = float(gates.get("minimum_quality_delta", 0.0))
    if float(fidelity.get("score", 0.0)) < min_fidelity:
        return False
    if fidelity.get("pass") is False:
        return False
    if float(quality.get("candidate_minus_source", -999.0)) < min_quality:
        return False
    if quality.get("pass") is False:
        return False
    if precheck.get("immutable_items_missing"):
        return False
    return True


def _base_value(row: dict[str, Any]) -> float:
    fidelity = float((row.get("fidelity") or {}).get("score", 0.0))
    quality_delta = float((row.get("quality") or {}).get("candidate_minus_source", 0.0))
    return fidelity + 0.08 * quality_delta


def _select_beam(
    candidates_by_id: dict[str, Candidate],
    ranking: list[dict[str, Any]],
    *,
    gates: dict[str, Any],
    beam_width: int,
    diversity_weight: float,
) -> list[str]:
    eligible = [row for row in ranking if _passes(row, gates)]
    if not eligible:
        # Preserve progress for inspection even when the hard gates reject everything.
        eligible = sorted(ranking, key=_base_value, reverse=True)[:beam_width]
    else:
        eligible = sorted(eligible, key=_base_value, reverse=True)

    selected: list[dict[str, Any]] = []
    remaining = eligible[:]
    while remaining and len(selected) < beam_width:
        if not selected:
            chosen = remaining.pop(0)
        else:
            def score(row: dict[str, Any]) -> float:
                text = candidates_by_id[row["candidate_id"]].text
                min_div = min(
                    pair_distance(text, candidates_by_id[s["candidate_id"]].text)
                    for s in selected
                )
                return _base_value(row) + diversity_weight * min_div

            chosen = max(remaining, key=score)
            remaining.remove(chosen)
        selected.append(chosen)
    return [row["candidate_id"] for row in selected]


def run_pipeline(
    exp: Experiment,
    providers: Provider | list[Provider],
    *,
    judge_provider: Provider | None = None,
    plans_n: int = 4,
    drafts_per_plan: int = 1,
    beam_width: int = 4,
    beam_rounds: int = 1,
    operators: list[str] | None = None,
    operators_per_candidate: int = 2,
    diversity_weight: float = 0.25,
    gates: dict[str, Any] | None = None,
) -> PipelineResult:
    provider_list = providers if isinstance(providers, list) else [providers]
    if not provider_list:
        raise ValueError("At least one provider is required")
    judge = judge_provider or provider_list[0]
    gates = gates or {"minimum_fidelity": 0.96, "minimum_quality_delta": 0.0}
    operators = operators or []

    source = (exp.root / "source.txt").read_text(encoding="utf-8")

    lock_prompt = render_skill("01_content_lock.md", SOURCE=source)
    content_lock = _json(judge.chat(lock_prompt, json_mode=True))
    write_json(exp.root / "content_lock.json", content_lock)

    plan_prompt = render_skill(
        "02_structure_planner.md",
        SOURCE=source,
        CONTENT_LOCK=json.dumps(content_lock, indent=2),
        PLAN_COUNT=str(plans_n),
    )
    plans_obj = _json(judge.chat(plan_prompt, json_mode=True))
    plans = plans_obj.get("plans", plans_obj if isinstance(plans_obj, list) else [])
    plans = plans[:plans_n]
    write_json(exp.root / "plans.json", {"plans": plans})

    candidates: list[Candidate] = []
    ranking: list[dict[str, Any]] = []
    candidates_by_id: dict[str, Candidate] = {}
    provider_cursor = 0

    for i, plan in enumerate(plans):
        for j in range(drafts_per_plan):
            generator = provider_list[provider_cursor % len(provider_list)]
            provider_cursor += 1
            draft_prompt = render_skill(
                "03_draft_writer.md",
                SOURCE=source,
                CONTENT_LOCK=json.dumps(content_lock, indent=2),
                PLAN=json.dumps(plan, indent=2),
            )
            draft = generator.chat(draft_prompt)
            cand = Candidate(
                text=draft,
                stage="draft",
                metadata={
                    "plan_index": i,
                    "draft_index": j,
                    "generator_model": generator.identity,
                    "structural_distance_from_source": structural_distance(source, draft),
                },
            )
            candidates.append(cand)
            candidates_by_id[cand.id] = cand
            ranking.append(_judge_candidate(exp, cand, source=source, content_lock=content_lock, judge_provider=judge))

            reviser = provider_list[provider_cursor % len(provider_list)]
            provider_cursor += 1
            revise_prompt = render_skill(
                "04_global_reviser.md",
                ORIGINAL_SOURCE=source,
                CONTENT_LOCK=json.dumps(content_lock, indent=2),
                DRAFT=draft,
            )
            revised = reviser.chat(revise_prompt)
            rc = Candidate(
                text=revised,
                stage="global_revision",
                parent_id=cand.id,
                metadata={
                    "plan_index": i,
                    "draft_index": j,
                    "generator_model": generator.identity,
                    "reviser_model": reviser.identity,
                    "structural_distance_from_parent": structural_distance(draft, revised),
                    "structural_distance_from_source": structural_distance(source, revised),
                },
            )
            candidates.append(rc)
            candidates_by_id[rc.id] = rc
            ranking.append(_judge_candidate(exp, rc, source=source, content_lock=content_lock, judge_provider=judge))

    beam_ids = _select_beam(
        candidates_by_id,
        ranking,
        gates=gates,
        beam_width=beam_width,
        diversity_weight=diversity_weight,
    )

    for round_index in range(beam_rounds):
        if not operators or not beam_ids:
            break
        new_rows: list[dict[str, Any]] = []
        parents = [candidates_by_id[cid] for cid in beam_ids]
        for parent_index, parent in enumerate(parents):
            for op_offset in range(min(operators_per_candidate, len(operators))):
                op_name = operators[(round_index + parent_index + op_offset) % len(operators)]
                transformer = provider_list[provider_cursor % len(provider_list)]
                provider_cursor += 1
                prompt = render_skill(
                    "08_operator_rewriter.md",
                    OPERATOR=load_operator(op_name),
                    CONTENT_LOCK=json.dumps(content_lock, indent=2),
                    CANDIDATE=parent.text,
                )
                text = transformer.chat(prompt)
                child = Candidate(
                    text=text,
                    stage="operator_revision",
                    parent_id=parent.id,
                    metadata={
                        "operator": op_name,
                        "beam_round": round_index + 1,
                        "reviser_model": transformer.identity,
                        "structural_distance_from_parent": structural_distance(parent.text, text),
                        "structural_distance_from_source": structural_distance(source, text),
                    },
                )
                candidates.append(child)
                candidates_by_id[child.id] = child
                row = _judge_candidate(exp, child, source=source, content_lock=content_lock, judge_provider=judge)
                ranking.append(row)
                new_rows.append(row)

        pool_ids = set(beam_ids) | {row["candidate_id"] for row in new_rows}
        pool_ranking = [row for row in ranking if row["candidate_id"] in pool_ids]
        beam_ids = _select_beam(
            candidates_by_id,
            pool_ranking,
            gates=gates,
            beam_width=beam_width,
            diversity_weight=diversity_weight,
        )

    selector_input = [row for row in ranking if row["candidate_id"] in set(beam_ids)]
    selector_prompt = render_skill("07_selector.md", CANDIDATES=json.dumps(selector_input, indent=2))
    selector = _json(judge.chat(selector_prompt, json_mode=True))
    selector["deterministic_beam_ids"] = beam_ids
    selector["beam_diversity"] = summarize_diversity([candidates_by_id[cid].text for cid in beam_ids]).to_dict()
    write_json(exp.root / "selection.json", selector)
    write_json(exp.root / "ranking.json", ranking)
    return PipelineResult(
        content_lock=content_lock,
        plans=plans,
        candidates=candidates,
        ranking=ranking,
        beam_ids=beam_ids,
    )
