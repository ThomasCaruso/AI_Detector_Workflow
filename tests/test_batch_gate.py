from authorship_shift.batch_gate import BatchGateConfig, assess_batch
from authorship_shift.candidate_lab import CandidateAnalysis


def _row(
    candidate_id: str,
    *,
    words: int = 100,
    pair: float = 0.2,
    immutables: float = 1.0,
    immutable_count: int = 4,
    nearest: float | None = None,
    nearest_id: str | None = "other",
):
    return CandidateAnalysis(
        candidate_id=candidate_id,
        word_count=words,
        sentence_count=5,
        sentence_length_cv=0.3,
        lexical_diversity=0.7,
        transition_start_ratio=0.1,
        generic_sentence_start_ratio=0.1,
        opening_repeat_ratio=0.1,
        opening_entropy=0.9,
        repeated_trigram_ratio=0.01,
        source_trigram_overlap=0.2,
        structural_distance_from_source=0.4,
        immutable_coverage=immutables,
        missing_immutables=[] if immutables == 1.0 else ["27%"],
        immutable_count=immutable_count,
        mean_pairwise_distance=pair,
        nearest_neighbor_distance=pair if nearest is None else nearest,
        nearest_neighbor_id=nearest_id,
    )


def test_batch_gate_passes_diverse_faithful_batch():
    report = assess_batch(
        [_row("a"), _row("b"), _row("c")],
        target_words=100,
    )
    assert report.pass_gate is True
    assert report.hard_failures == []


def test_batch_gate_rejects_profile_collapse():
    report = assess_batch(
        [_row("a", pair=0.02), _row("b", pair=0.03), _row("c", pair=0.01)],
        target_words=100,
    )
    assert report.pass_gate is False
    assert any("collapsed" in failure for failure in report.hard_failures)


def test_batch_gate_rejects_missing_immutable_and_bad_length():
    report = assess_batch(
        [_row("a"), _row("b"), _row("c", words=160, immutables=0.5)],
        target_words=100,
    )
    assert report.pass_gate is False
    assert "c" in report.candidate_failures
    joined = " ".join(report.candidate_failures["c"])
    assert "immutable_coverage" in joined
    assert "word_count" in joined


def test_batch_gate_rejects_near_duplicate_pair_hidden_by_a_healthy_mean():
    """Two collapsed candidates must not survive because the mean looks fine."""

    report = assess_batch(
        [
            _row("a", pair=0.40, nearest=0.01, nearest_id="b"),
            _row("b", pair=0.40, nearest=0.01, nearest_id="a"),
            _row("c", pair=0.45, nearest=0.40, nearest_id="a"),
        ],
        target_words=100,
    )
    assert report.mean_pairwise_distance > 0.10
    assert report.pass_gate is False
    joined = " ".join(report.hard_failures)
    assert "near-duplicate" in joined
    assert "a~b" in joined and "b~a" in joined


def test_batch_gate_reports_vacuous_fidelity_evidence():
    """Coverage 1.0 with nothing checkable is not verified fidelity."""

    report = assess_batch(
        [_row(cid, immutable_count=0) for cid in ("a", "b", "c")],
        target_words=100,
    )
    assert report.pass_gate is True
    assert report.fidelity_evidence == "vacuous"
    assert any("vacuous" in warning for warning in report.warnings)


def test_batch_gate_reports_checked_fidelity_evidence():
    report = assess_batch([_row("a"), _row("b"), _row("c")], target_words=100)
    assert report.fidelity_evidence == "checked"
    assert not any("vacuous" in warning for warning in report.warnings)


def test_batch_gate_thresholds_are_configurable():
    config = BatchGateConfig(
        min_candidates=2,
        min_mean_pairwise_distance=0.01,
        min_nearest_neighbor_distance=0.01,
    )
    report = assess_batch(
        [_row("a", pair=0.02), _row("b", pair=0.02)],
        config=config,
    )
    assert report.pass_gate is True
