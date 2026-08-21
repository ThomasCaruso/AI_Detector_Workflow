"""Ground-truth tests for the distribution-collapse diagnostics.

Each fixture below is constructed so the correct answer is known in advance:
one batch where profile labels genuinely track writing style, and one where the
labels are decorative because every candidate shares the same style.
"""

import pytest

from authorship_shift.collapse import (
    COMPOSITE,
    STYLISTIC,
    analyze_profile_separation,
    assess_collapse,
    permutation_resolution,
    style_distance,
    style_vector,
)

# Profiles that genuinely differ: clipped sentences, long semicolon-heavy
# sentences, and transition-led sentences. Within each profile the two samples
# differ in wording but share a shape.
SEPARATED = [
    (
        "s1",
        "clipped",
        "Costs rose. Margins fell. Demand slowed. The plan changed. "
        "Buyers waited. Nothing improved. The quarter closed.",
    ),
    (
        "s2",
        "clipped",
        "Prices climbed. Profits sank. Orders thinned. The plan shifted. "
        "Buyers paused. Little improved. The period ended.",
    ),
    (
        "l1",
        "periodic",
        "The steady climb in input costs eventually worked its way through every "
        "downstream line item in the quarter, and by the time the finance team "
        "reconciled the ledger the margin compression had already become the "
        "dominant story; buyers, who had been patient through two earlier "
        "adjustments, began to reconsider whether the standing contract terms "
        "still made any sense for them at all.",
    ),
    (
        "l2",
        "periodic",
        "A slow accumulation of supplier increases eventually reached each of the "
        "downstream categories in that same window, and once the accounting group "
        "finished its reconciliation the compressed margin had turned into the "
        "central finding; purchasers, having absorbed two prior revisions without "
        "complaint, started to question whether the existing agreement remained "
        "worth renewing on those terms.",
    ),
    (
        "t1",
        "transitional",
        "However, the input costs continued to climb throughout the reporting "
        "period. Therefore, the reported margin fell sharply against the prior "
        "year. Moreover, buyers began to reconsider the standing contract terms. "
        "Consequently, the finance team revisited its reconciliation approach.",
    ),
    (
        "t2",
        "transitional",
        "However, supplier prices kept rising across the whole reporting window. "
        "Therefore, the stated margin dropped noticeably against last year. "
        "Moreover, purchasers started to question the existing agreement terms. "
        "Consequently, the accounting group reviewed its reconciliation method.",
    ),
]

# Six stylistically homogeneous paragraphs. The profile labels are decorative:
# they carry no information about how any candidate is written.
_COLLAPSED_TEXTS = [
    "The rebate program ended in December and the effect showed up first in unit "
    "economics. Reported growth stayed flat for another two quarters after that. "
    "Management treated the gap as a timing issue rather than a trend. Buyers "
    "reached a different conclusion about the same numbers.",
    "The subsidy expired at year end and the impact appeared first in per-unit "
    "margins. Headline growth held steady for roughly two more quarters. Leadership "
    "read the shortfall as a timing artifact instead of a pattern. Purchasers drew "
    "another conclusion from those same figures.",
    "The incentive scheme lapsed in December and the consequence surfaced first in "
    "unit costs. Stated growth remained level for about two further quarters. The "
    "executives framed the shortfall as timing rather than direction. Acquirers "
    "took a different view of the identical data.",
    "The credit arrangement finished at year close and the result emerged first in "
    "per-unit figures. Published growth stayed even for nearly two additional "
    "quarters. Managers described the gap as a scheduling effect not a trajectory. "
    "Investors formed another judgment about the same disclosures.",
    "The discount program concluded in December and the outcome registered first in "
    "unit margins. Recorded growth was flat for some two quarters afterward. The "
    "board characterized the shortfall as timing instead of a real decline. Bidders "
    "arrived at a separate reading of those figures.",
    "The rebate scheme terminated at year end and the effect landed first on "
    "per-unit economics. Disclosed growth remained steady for close to two more "
    "quarters. Officers explained the gap as a timing matter rather than a slide. "
    "Counterparties settled on a different interpretation of the data.",
]

COLLAPSED = [
    (f"c{i + 1}", label, text)
    for i, (label, text) in enumerate(
        zip(["alpha", "alpha", "beta", "beta", "gamma", "gamma"], _COLLAPSED_TEXTS)
    )
]


def test_style_vector_is_bounded_and_fixed_width():
    vector = style_vector(SEPARATED[0][2])
    assert len(vector) == 14
    assert all(0.0 <= value <= 1.0 for value in vector)


def test_style_distance_separates_shapes_it_should():
    clipped, periodic = SEPARATED[0][2], SEPARATED[2][2]
    clipped_twin = SEPARATED[1][2]
    assert style_distance(clipped, clipped_twin) < style_distance(clipped, periodic)


def test_separation_detects_real_profile_effects():
    result = analyze_profile_separation(SEPARATED, distance_mode=STYLISTIC, permutations=500)
    assert result.between_profile_mean > result.within_profile_mean
    assert result.separation_ratio > 1.5
    assert result.p_value is not None and result.p_value < 0.10
    assert "separated" in result.interpretation


def test_permutation_resolution_is_reported():
    """A 3x2 design cannot reach a small p-value however large the effect."""

    result = analyze_profile_separation(SEPARATED, permutations=500)
    assert result.distinct_groupings == 90
    # Relabeling the three equal groups reproduces the same partition, so those
    # 3! permutations always tie with the observed ratio.
    assert result.min_achievable_p == pytest.approx(6 / 90)
    assert result.design_has_resolution is False
    assert result.p_value >= result.min_achievable_p


def test_five_by_two_design_has_permutation_resolution():
    """The recommended 5 profiles x 2 samples batch is adequately powered."""

    labels = [f"p{i}" for i in range(1, 6) for _ in range(2)]
    groupings, min_p = permutation_resolution(labels)
    assert groupings == 113400
    assert min_p == pytest.approx(120 / 113400)
    assert min_p <= 0.05


def test_large_effect_is_not_called_collapsed_when_underpowered():
    """The p-value must not veto a real effect the design could never confirm."""

    result = analyze_profile_separation(SEPARATED, permutations=500)
    assert result.separation_ratio > 10
    assert "collapsed" not in result.interpretation


def test_collapse_report_flags_underpowered_designs():
    report = assess_collapse(SEPARATED, permutations=300)
    assert any("underpowered" in note for note in report.notes)


def test_separation_reports_collapse_when_labels_are_decorative():
    result = analyze_profile_separation(COLLAPSED, distance_mode=STYLISTIC, permutations=500)
    assert result.separation_ratio < 1.25
    assert result.p_value is not None and result.p_value > 0.10
    assert "collapsed" in result.interpretation


def test_separation_requires_replicates():
    one_per_profile = [
        ("a", "alpha", SEPARATED[0][2]),
        ("b", "beta", SEPARATED[2][2]),
        ("c", "gamma", SEPARATED[4][2]),
    ]
    with pytest.raises(ValueError, match="replicates"):
        analyze_profile_separation(one_per_profile)


def test_separation_is_deterministic_for_a_seed():
    first = analyze_profile_separation(SEPARATED, permutations=200, seed=7)
    second = analyze_profile_separation(SEPARATED, permutations=200, seed=7)
    assert first.p_value == second.p_value
    assert first.separation_ratio == second.separation_ratio


def test_assess_collapse_reports_both_distance_modes():
    report = assess_collapse(SEPARATED, permutations=300)
    assert report.replicates_available is True
    assert report.profiles_with_replicates == 3
    assert {row.distance_mode for row in report.separations} == {STYLISTIC, COMPOSITE}
    assert report.duplicate_pairs == []


def test_assess_collapse_refuses_to_guess_without_replicates():
    one_per_profile = [
        ("a", "alpha", SEPARATED[0][2]),
        ("b", "beta", SEPARATED[2][2]),
        ("c", "gamma", SEPARATED[4][2]),
    ]
    report = assess_collapse(one_per_profile)
    assert report.replicates_available is False
    assert report.separations == []
    assert any("two or more candidates" in note for note in report.notes)


def test_assess_collapse_flags_near_duplicates():
    duplicated = list(SEPARATED) + [("s3", "clipped", SEPARATED[0][2])]
    report = assess_collapse(duplicated, permutations=100)
    assert any(pair[2] < 0.05 for pair in report.duplicate_pairs)
    assert any("near-duplicate" in note for note in report.notes)
