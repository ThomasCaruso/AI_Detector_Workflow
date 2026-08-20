from authorship_shift.confidence import exact_two_sided_sign_test, paired_metric_summary


def _rows():
    rows = []
    for i in range(6):
        rows.append({
            "variant": "baseline", "sample_id": str(i),
            "hard_gate_pass_rate": 0.5, "mean_fidelity": 0.90,
            "mean_quality_delta": 0.0, "mean_structural_distance": 0.2,
            "beam_mean_pair_distance": 0.1, "candidate_count": 10,
        })
        rows.append({
            "variant": "full", "sample_id": str(i),
            "hard_gate_pass_rate": 0.8, "mean_fidelity": 0.95,
            "mean_quality_delta": 1.0, "mean_structural_distance": 0.3,
            "beam_mean_pair_distance": 0.2, "candidate_count": 12,
        })
    return rows


def test_sign_test_all_wins():
    assert exact_two_sided_sign_test([1, 1, 1, 1, 1, 1]) == 0.03125


def test_paired_summary_orients_lower_candidate_count_as_better():
    summary = paired_metric_summary(
        _rows(), "baseline", "full", "candidate_count",
        higher_is_better=False, resamples=100, seed="test",
    )
    assert summary["paired_samples"] == 6
    assert summary["raw_mean_delta"] == 2.0
    assert summary["oriented_mean_improvement"] == -2.0
    assert summary["challenger_win_rate"] == 0.0
