from authorship_shift.batch_gate import BatchGateConfig, assess_batch
from authorship_shift.candidate_lab import CandidateAnalysis


def _row(candidate_id: str, *, words: int = 100, pair: float = 0.2, immutables: float = 1.0):
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
        mean_pairwise_distance=pair,
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


def test_batch_gate_thresholds_are_configurable():
    config = BatchGateConfig(min_candidates=2, min_mean_pairwise_distance=0.01)
    report = assess_batch(
        [_row("a", pair=0.02), _row("b", pair=0.02)],
        config=config,
    )
    assert report.pass_gate is True
