"""Tests for deterministic candidate reranking.

The documented selection philosophy forbids treating diagnostics as quality
targets, so these tests pin down the property that matters most: a candidate
must never be able to win by pushing a metric to an extreme.
"""

import pytest

from authorship_shift.candidate_lab import CandidateAnalysis
from authorship_shift.rerank import RerankConfig, rerank, score_candidate


def _analysis(candidate_id: str, **overrides) -> CandidateAnalysis:
    values = dict(
        word_count=300,
        sentence_count=14,
        sentence_length_cv=0.45,
        lexical_diversity=0.62,
        transition_start_ratio=0.05,
        generic_sentence_start_ratio=0.07,
        opening_repeat_ratio=0.05,
        opening_entropy=0.95,
        repeated_trigram_ratio=0.0,
        source_trigram_overlap=0.10,
        structural_distance_from_source=0.30,
        immutable_coverage=1.0,
        missing_immutables=[],
        immutable_count=6,
    )
    values.update(overrides)
    return CandidateAnalysis(candidate_id=candidate_id, **values)


def test_clean_candidate_has_no_defects():
    score = score_candidate(_analysis("clean"))
    assert score.eligible is True
    assert score.defect_score == 0.0
    assert score.defects == []


def test_defects_accumulate_for_bad_values():
    score = score_candidate(
        _analysis(
            "noisy",
            transition_start_ratio=0.40,
            opening_repeat_ratio=0.50,
            source_trigram_overlap=0.70,
        )
    )
    assert score.defect_score > 0
    joined = " ".join(score.defects)
    assert "transition_start_ratio" in joined
    assert "source_trigram_overlap" in joined


def test_extreme_metrics_are_never_rewarded():
    """Pushing a diagnostic to an extreme must not beat ordinary prose."""

    ordinary = score_candidate(
        _analysis("ordinary", transition_start_ratio=0.10, lexical_diversity=0.55)
    )
    extreme = score_candidate(
        _analysis(
            "extreme",
            transition_start_ratio=0.0,
            lexical_diversity=0.99,
            structural_distance_from_source=1.0,
        )
    )
    assert ordinary.defect_score == extreme.defect_score == 0.0


def test_fidelity_and_length_failures_are_rejected():
    lost_detail = score_candidate(
        _analysis("lost", immutable_coverage=0.8, missing_immutables=["27%"])
    )
    assert lost_detail.eligible is False
    assert any("immutable_coverage" in reason for reason in lost_detail.rejections)

    wrong_length = score_candidate(_analysis("short", word_count=120), target_words=300)
    assert wrong_length.eligible is False
    assert any("word_count" in reason for reason in wrong_length.rejections)


def test_rerank_orders_by_defects_and_shortlists():
    texts = {
        "a": "Costs rose through the period. Buyers noticed the change late. "
             "The rebate expiry explains most of it.",
        "b": "However, costs rose. However, buyers noticed. However, the rebate expired.",
        "c": "A rebate expiry drove most of the increase; buyers registered it only "
             "after the quarter had closed, which delayed the response.",
    }
    analyses = [
        _analysis("a"),
        _analysis("b", transition_start_ratio=0.9, opening_repeat_ratio=0.66, opening_entropy=0.2),
        _analysis("c"),
    ]
    result = rerank(list(texts.items()), analyses, select=2)

    assert result.ranked[-1].candidate_id == "b"
    assert "b" not in result.selected
    assert len(result.selected) == 2
    assert result.eligible_count == 3


def test_rerank_prefers_distant_candidates_among_equals():
    """Given equal quality, the shortlist must not be near-duplicates."""

    twin = "Costs rose sharply. Margins fell. Demand slowed after the change."
    texts = {
        "a": twin,
        "b": twin + " Buyers waited.",
        "c": "A rebate expiry drove most of the increase; buyers registered it only "
             "after the quarter closed, which delayed every downstream response.",
    }
    analyses = [_analysis("a"), _analysis("b"), _analysis("c")]
    result = rerank(list(texts.items()), analyses, select=2)

    assert result.selected[0] == "a"
    assert result.selected[1] == "c"


def test_rerank_returns_nothing_when_no_candidate_is_eligible():
    texts = {"a": "Some prose.", "b": "Other prose."}
    analyses = [
        _analysis("a", immutable_coverage=0.5, missing_immutables=["27%"]),
        _analysis("b", immutable_coverage=0.0, missing_immutables=["27%", "2025"]),
    ]
    result = rerank(list(texts.items()), analyses, select=2)

    assert result.selected == []
    assert result.eligible_count == 0
    assert result.rejected_count == 2
    assert any("no candidate satisfied" in note for note in result.notes)


def test_rerank_always_flags_what_it_cannot_judge():
    texts = {"a": "Some prose here.", "b": "Different prose entirely."}
    result = rerank(list(texts.items()), [_analysis("a"), _analysis("b")], select=2)
    assert any("voice match" in note for note in result.notes)


def test_rerank_is_deterministic():
    texts = {"a": "Alpha prose.", "b": "Beta prose here.", "c": "Gamma prose there."}
    analyses = [_analysis("a"), _analysis("b"), _analysis("c")]
    first = rerank(list(texts.items()), analyses, select=3)
    second = rerank(list(texts.items()), analyses, select=3)
    assert first.selected == second.selected


def test_rerank_requires_text_for_every_analysis():
    with pytest.raises(ValueError, match="no text supplied"):
        rerank([("a", "Alpha prose.")], [_analysis("a"), _analysis("b")])


def test_rerank_thresholds_are_configurable():
    strict = RerankConfig(min_immutable_coverage=0.5)
    score = score_candidate(
        _analysis("partial", immutable_coverage=0.6, missing_immutables=["27%"]),
        config=strict,
    )
    assert score.eligible is True
