"""Exact paired nonparametric tests for very small samples.

At n = 8 the normal approximation most libraries use is wrong in the direction
that matters: it is anti-conservative in the tail, so a borderline result can be
reported as significant when the exact distribution says otherwise. These
experiments decide on p < 0.05 with eight paired documents, so the exact null
distribution is enumerated rather than approximated.

Enumeration is 2**n sign assignments. That is 256 at n = 8 and stays tractable
well past any sample this corpus will produce; :func:`wilcoxon_signed_rank_exact`
refuses rather than silently approximating if asked for more than it can
enumerate.

Tie handling is explicit because it changes the answer:

* pairs with a difference of exactly zero are dropped before ranking, which
  reduces n and is reported;
* ties among absolute differences receive average ranks, and the null
  distribution is then enumerated over sign assignments to those fixed ranks.
  Re-ranking under each assignment would be a different test.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
import math
from typing import Sequence

MAX_ENUMERATED_N = 24


@dataclass(frozen=True)
class ExactTestResult:
    """Outcome of an exact paired test."""

    statistic: float
    p_value: float
    n_used: int
    n_dropped_zero: int
    alternative: str
    method: str

    @property
    def significant_at_05(self) -> bool:
        return self.p_value < 0.05


def _average_ranks(values: Sequence[float]) -> list[float]:
    """Ranks 1..n, ties sharing their average."""

    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        shared = (i + 1 + j + 1) / 2
        for k in range(i, j + 1):
            ranks[order[k]] = shared
        i = j + 1
    return ranks


def wilcoxon_signed_rank_exact(
    differences: Sequence[float], *, alternative: str = "greater"
) -> ExactTestResult:
    """One-sided exact Wilcoxon signed-rank test on paired differences.

    ``alternative="greater"`` tests whether the differences are centred above
    zero. The statistic is W+, the sum of ranks of positive differences, and the
    p-value is the exact probability of a W+ at least as extreme under the null
    that each sign is equally likely.
    """

    if alternative not in ("greater", "less"):
        raise ValueError(f"unsupported alternative {alternative!r}")

    kept = [d for d in differences if d != 0]
    dropped = len(differences) - len(kept)
    if not kept:
        return ExactTestResult(0.0, 1.0, 0, dropped, alternative, "exact-wilcoxon-signed-rank")
    if len(kept) > MAX_ENUMERATED_N:
        raise ValueError(
            f"{len(kept)} nonzero pairs exceeds the enumeration limit "
            f"{MAX_ENUMERATED_N}; this function will not approximate"
        )

    if alternative == "less":
        kept = [-d for d in kept]

    ranks = _average_ranks([abs(d) for d in kept])
    observed = sum(r for r, d in zip(ranks, kept) if d > 0)

    at_least_as_extreme = 0
    for signs in product((0, 1), repeat=len(kept)):
        w = sum(r for r, s in zip(ranks, signs) if s)
        if w >= observed - 1e-12:
            at_least_as_extreme += 1
    p = at_least_as_extreme / (2 ** len(kept))

    return ExactTestResult(
        statistic=observed, p_value=p, n_used=len(kept), n_dropped_zero=dropped,
        alternative=alternative, method="exact-wilcoxon-signed-rank",
    )


def sign_test_exact(
    differences: Sequence[float], *, alternative: str = "greater"
) -> ExactTestResult:
    """One-sided exact sign test. Reported alongside Wilcoxon, never instead of it."""

    kept = [d for d in differences if d != 0]
    dropped = len(differences) - len(kept)
    if not kept:
        return ExactTestResult(0.0, 1.0, 0, dropped, alternative, "exact-sign-test")
    wins = sum(1 for d in kept if (d > 0 if alternative == "greater" else d < 0))
    n = len(kept)
    p = sum(math.comb(n, k) for k in range(wins, n + 1)) / 2**n
    return ExactTestResult(float(wins), p, n, dropped, alternative, "exact-sign-test")


def non_inferiority_wilcoxon_exact(
    differences: Sequence[float], *, margin: float
) -> ExactTestResult:
    """Exact one-sided non-inferiority test at a prespecified margin.

    ``differences`` are treatment minus control. The null is that treatment is
    worse than control by at least ``margin``; the test shifts each difference
    up by the margin and asks whether the shifted values are centred above zero.
    A pass therefore means degradation is demonstrably smaller than the margin,
    not merely that no degradation happened to be observed.
    """

    if margin <= 0:
        raise ValueError("non-inferiority margin must be positive")
    shifted = [d + margin for d in differences]
    result = wilcoxon_signed_rank_exact(shifted, alternative="greater")
    return ExactTestResult(
        statistic=result.statistic, p_value=result.p_value, n_used=result.n_used,
        n_dropped_zero=result.n_dropped_zero, alternative="greater",
        method=f"exact-wilcoxon-non-inferiority(margin={margin})",
    )
