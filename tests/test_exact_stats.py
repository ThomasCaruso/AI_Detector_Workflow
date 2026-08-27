"""Tests for exact paired nonparametric tests. Synthetic numbers only."""

from __future__ import annotations

import math

import pytest

from authorship_shift.exact_stats import (
    MAX_ENUMERATED_N,
    non_inferiority_wilcoxon_exact,
    sign_test_exact,
    wilcoxon_signed_rank_exact,
)


def test_all_positive_at_n8_gives_the_floor_p_value():
    r = wilcoxon_signed_rank_exact([1, 2, 3, 4, 5, 6, 7, 8])

    assert r.n_used == 8
    assert r.statistic == 36
    assert r.p_value == pytest.approx(1 / 256)


def test_one_small_negative_at_n8_stays_significant():
    """Wilcoxon can survive one adverse pair when magnitudes favour treatment."""

    r = wilcoxon_signed_rank_exact([-1, 2, 3, 4, 5, 6, 7, 8])

    assert r.statistic == 35
    assert r.p_value == pytest.approx(2 / 256)
    assert r.significant_at_05


def test_all_negative_gives_p_one():
    assert wilcoxon_signed_rank_exact([-1, -2, -3]).p_value == pytest.approx(1.0)


def test_zero_differences_are_dropped_and_reported():
    r = wilcoxon_signed_rank_exact([0, 0, 1, 2, 3])

    assert r.n_dropped_zero == 2
    assert r.n_used == 3


def test_all_zero_differences_yield_no_evidence():
    r = wilcoxon_signed_rank_exact([0, 0, 0])

    assert r.n_used == 0
    assert r.p_value == 1.0
    assert not r.significant_at_05


def test_tied_absolute_differences_use_average_ranks():
    """Two pairs tied at |1| share rank 1.5, so W+ is fractional."""

    r = wilcoxon_signed_rank_exact([1, -1, 3])

    assert r.statistic == pytest.approx(1.5 + 3)


def test_ranks_are_fixed_across_enumeration():
    """The null enumerates signs over fixed ranks, not re-ranked samples."""

    r = wilcoxon_signed_rank_exact([2, 2, 2])
    # three tied pairs share rank 2.0; all-positive W+ = 6.0, p = 1/8
    assert r.statistic == pytest.approx(6.0)
    assert r.p_value == pytest.approx(1 / 8)


def test_less_alternative_mirrors_greater():
    a = wilcoxon_signed_rank_exact([1, 2, 3], alternative="greater")
    b = wilcoxon_signed_rank_exact([-1, -2, -3], alternative="less")

    assert a.p_value == pytest.approx(b.p_value)


def test_unsupported_alternative_rejected():
    with pytest.raises(ValueError, match="unsupported alternative"):
        wilcoxon_signed_rank_exact([1, 2], alternative="two-sided")


def test_refuses_to_approximate_beyond_the_enumeration_limit():
    with pytest.raises(ValueError, match="will not approximate"):
        wilcoxon_signed_rank_exact(list(range(1, MAX_ENUMERATED_N + 2)))


def test_p_value_is_monotone_in_the_statistic():
    weak = wilcoxon_signed_rank_exact([-3, -2, 1, 2, 3, 4, 5, 6])
    strong = wilcoxon_signed_rank_exact([1, 2, 3, 4, 5, 6, 7, 8])

    assert strong.p_value < weak.p_value


# --- sign test -------------------------------------------------------------

def test_sign_test_matches_the_binomial_tail():
    r = sign_test_exact([1, 1, 1, 1, 1, 1, 1, -1])

    assert r.n_used == 8
    expected = sum(math.comb(8, k) for k in range(7, 9)) / 256
    assert r.p_value == pytest.approx(expected)


def test_sign_test_at_seven_of_eight_is_significant():
    assert sign_test_exact([1] * 7 + [-1]).p_value == pytest.approx(0.03515625)


def test_sign_test_at_six_of_eight_is_not():
    assert not sign_test_exact([1] * 6 + [-1, -1]).significant_at_05


# --- non-inferiority -------------------------------------------------------

def test_non_inferiority_passes_when_losses_are_smaller_than_the_margin():
    """Every document loses 0.05 style points against a 0.20 margin."""

    r = non_inferiority_wilcoxon_exact([-0.05] * 8, margin=0.20)

    assert r.p_value == pytest.approx(1 / 256)
    assert r.significant_at_05


def test_non_inferiority_fails_when_losses_exceed_the_margin():
    r = non_inferiority_wilcoxon_exact([-0.5] * 8, margin=0.20)

    assert not r.significant_at_05


def test_non_inferiority_fails_on_a_mixed_result_with_large_losses():
    """Winning some documents does not rescue material losses elsewhere."""

    r = non_inferiority_wilcoxon_exact([0.4, 0.4, 0.4, 0.4, -1.0, -1.0, -1.0, -1.0], margin=0.20)

    assert not r.significant_at_05


def test_non_inferiority_records_its_margin_in_the_method():
    r = non_inferiority_wilcoxon_exact([0.1] * 4, margin=0.20)

    assert "margin=0.2" in r.method


def test_non_inferiority_rejects_a_nonpositive_margin():
    with pytest.raises(ValueError, match="margin must be positive"):
        non_inferiority_wilcoxon_exact([0.1], margin=0.0)


def test_exact_zero_shifted_difference_is_dropped():
    """A difference of exactly -margin shifts to zero and drops out."""

    r = non_inferiority_wilcoxon_exact([-0.20, 0.1, 0.1], margin=0.20)

    assert r.n_dropped_zero == 1
    assert r.n_used == 2
