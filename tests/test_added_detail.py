from authorship_shift.added_detail import added_name_hits
from authorship_shift.batch_gate import BatchGateConfig, assess_batch
from authorship_shift.candidate_lab import analyze_candidates, extract_immutables


def test_added_name_detector_catches_mid_sentence_companies():
    source = "Competition can shorten development cycles when rivals raise the cost of delay."
    candidate = (
        "Competition can shorten development cycles; when Sony and Toshiba pursue "
        "the same market, each firm has a reason to move faster."
    )
    assert added_name_hits(source, candidate) == ["Sony", "Toshiba"]


def test_added_name_detector_ignores_source_names_and_clause_initial_capitals():
    source = "Atlas implementation moves after validation."
    candidate = "Atlas moves after validation. However, timing remains uncertain."
    assert added_name_hits(source, candidate) == []


def test_batch_gate_rejects_candidate_with_unsupported_added_name():
    source = "Competition can shorten development cycles when rivals raise the cost of delay."
    candidates = [
        ("a", "Competition can shorten development cycles because delay becomes costly."),
        ("b", "Rivalry can make a technical bottleneck more urgent without guaranteeing progress."),
        (
            "c",
            "Competition can shorten development cycles when Sony enters a contested market.",
        ),
    ]
    analyses = analyze_candidates(source, candidates)
    report = assess_batch(
        analyses,
        config=BatchGateConfig(
            min_mean_pairwise_distance=0.0,
            min_nearest_neighbor_distance=0.0,
        ),
    )
    assert report.pass_gate is False
    assert "c" in report.candidate_failures
    assert any("unsupported added name" in item for item in report.candidate_failures["c"])


def test_leading_article_is_not_part_of_atlas_immutable():
    source = (
        "The Atlas implementation was scheduled for September 14. "
        "The vendor now expects the export on September 16."
    )
    items = extract_immutables(source)
    assert "The Atlas" not in items
    assert "Atlas" in items
    assert "14" in items
    assert "16" in items
