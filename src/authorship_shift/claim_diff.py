from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any

from .metrics import words

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "been", "but", "by",
    "can", "could", "do", "does", "for", "from", "had", "has", "have", "he", "her",
    "his", "i", "if", "in", "into", "is", "it", "its", "may", "more", "most", "not",
    "of", "on", "or", "our", "she", "should", "so", "than", "that", "the", "their",
    "them", "there", "these", "they", "this", "to", "was", "we", "were", "what",
    "when", "which", "who", "will", "with", "would", "you", "your",
}


def _content_tokens(text: str) -> set[str]:
    return {t for t in words(text) if len(t) > 2 and t not in STOPWORDS}


def _claim_text(claim: Any) -> str:
    if isinstance(claim, str):
        return claim
    if isinstance(claim, dict):
        for key in ("proposition", "claim", "text", "statement"):
            if claim.get(key):
                return str(claim[key])
    return str(claim)


def _claim_id(claim: Any, index: int) -> str:
    if isinstance(claim, dict):
        for key in ("id", "claim_id", "stable_id"):
            if claim.get(key):
                return str(claim[key])
    return f"C{index + 1}"


def _claim_importance(claim: Any) -> str:
    if isinstance(claim, dict):
        return str(claim.get("importance", "supporting"))
    return "supporting"


def _immutable_strings(content_lock: dict[str, Any]) -> list[str]:
    raw = content_lock.get("immutable_items", []) or []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            for key in ("value", "text", "item", "exact"):
                value = item.get(key)
                if value is not None:
                    out.append(str(value))
                    break
    return [x for x in out if x.strip()]


@dataclass
class ClaimCoverage:
    claim_id: str
    importance: str
    lexical_recall: float
    matched_terms: list[str]
    missing_terms: list[str]
    warning: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ClaimDiffReport:
    required_claims: int
    required_claims_warned: int
    mean_required_lexical_recall: float
    immutable_items_total: int
    immutable_items_missing: list[str]
    claims: list[ClaimCoverage]
    note: str = (
        "Deterministic lexical prefilter only. A clean report does not prove semantic fidelity, "
        "and a warning does not prove a claim was lost. Use the semantic judge for final gating."
    )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["claims"] = [c.to_dict() for c in self.claims]
        return data


def claim_coverage_report(content_lock: dict[str, Any], candidate_text: str, *, warning_threshold: float = 0.45) -> ClaimDiffReport:
    candidate_tokens = _content_tokens(candidate_text)
    reports: list[ClaimCoverage] = []

    for i, claim in enumerate(content_lock.get("claims", []) or []):
        text = _claim_text(claim)
        claim_tokens = _content_tokens(text)
        matched = sorted(claim_tokens & candidate_tokens)
        missing = sorted(claim_tokens - candidate_tokens)
        recall = (len(matched) / len(claim_tokens)) if claim_tokens else 1.0
        importance = _claim_importance(claim)
        reports.append(ClaimCoverage(
            claim_id=_claim_id(claim, i),
            importance=importance,
            lexical_recall=round(recall, 4),
            matched_terms=matched,
            missing_terms=missing,
            warning=(importance == "required" and recall < warning_threshold),
        ))

    required = [r for r in reports if r.importance == "required"]
    mean_required = sum(r.lexical_recall for r in required) / len(required) if required else 1.0

    immutable_items = _immutable_strings(content_lock)
    candidate_lower = candidate_text.lower()
    missing_immutables = [x for x in immutable_items if x.lower() not in candidate_lower]

    return ClaimDiffReport(
        required_claims=len(required),
        required_claims_warned=sum(1 for r in required if r.warning),
        mean_required_lexical_recall=round(mean_required, 4),
        immutable_items_total=len(immutable_items),
        immutable_items_missing=missing_immutables,
        claims=reports,
    )
