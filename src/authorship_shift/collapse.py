"""Distribution-collapse diagnostics for Engine v2 candidate batches.

The engine's central research question is whether independent generations plus
profile and sampling variation actually move the output, or whether everything
falls back into one model writing distribution. Mean pairwise distance cannot
answer that. A batch can post a healthy mean while the profile directives do
nothing, because the spread comes from ordinary sampling noise rather than from
the profiles.

The statistic that separates those two worlds is the ratio of between-profile
dispersion to within-profile dispersion:

* ratio near 1.0 - profile directives move candidates no further than resampling
  the same profile does. The profiles are decorative and the model distribution
  dominates.
* ratio well above 1.0 - profiles carve out genuinely different regions.

Measuring it requires at least two candidates for at least one profile. A batch
of one-sample-per-profile has no within-profile term and cannot be assessed.

The ratio is reported alongside a permutation test so it is a statistic rather
than an impression. Nothing here is an authorship classifier or a detector
surrogate; these are engineering diagnostics computed locally at zero cost.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from itertools import combinations
from math import factorial
import random
from typing import Any, Sequence

from .candidate_lab import generic_sentence_start_ratio, opening_entropy, opening_repeat_ratio
from .diversity import pair_distance
from .metrics import measure

# Each entry is (metric name, divisor used to bring the value into roughly 0..1).
# Ratios and coefficients of variation are already on that scale.
STYLE_FIELDS: tuple[tuple[str, float], ...] = (
    ("sentence_length_mean", 40.0),
    ("sentence_length_cv", 1.0),
    ("paragraph_length_mean", 200.0),
    ("paragraph_length_cv", 1.0),
    ("short_sentence_ratio", 1.0),
    ("long_sentence_ratio", 1.0),
    ("repeated_trigram_ratio", 1.0),
    ("transition_start_ratio", 1.0),
    ("semicolons_per_1k_words", 20.0),
    ("em_dashes_per_1k_words", 20.0),
    ("lexical_diversity", 1.0),
)

STYLE_FIELD_NAMES: tuple[str, ...] = tuple(name for name, _ in STYLE_FIELDS) + (
    "generic_sentence_start_ratio",
    "opening_repeat_ratio",
    "opening_entropy",
)

DistanceMode = str
COMPOSITE: DistanceMode = "composite"
STYLISTIC: DistanceMode = "stylistic"


def style_vector(text: str) -> list[float]:
    """Return a fixed-order, roughly 0..1 style descriptor for one text.

    The vector deliberately excludes topic and content signals. Two candidates
    expressing the same locked content differ here only in how the prose is
    shaped.
    """

    metrics = measure(text)
    vector = [
        min(float(getattr(metrics, name)) / divisor, 1.0) for name, divisor in STYLE_FIELDS
    ]
    vector.append(generic_sentence_start_ratio(text))
    vector.append(opening_repeat_ratio(text))
    vector.append(opening_entropy(text))
    return vector


def style_distance(a: str, b: str) -> float:
    """Mean absolute difference between two style vectors, in 0..1."""

    va, vb = style_vector(a), style_vector(b)
    return sum(abs(x - y) for x, y in zip(va, vb)) / len(va)


def _distance_for_mode(mode: DistanceMode):
    if mode == COMPOSITE:
        return pair_distance
    if mode == STYLISTIC:
        return style_distance
    raise ValueError(f"unknown distance mode {mode!r}; expected {COMPOSITE!r} or {STYLISTIC!r}")


@dataclass
class ProfileSeparation:
    """Between-profile versus within-profile dispersion for one distance mode."""

    distance_mode: DistanceMode
    within_profile_mean: float
    between_profile_mean: float
    separation_ratio: float
    within_pair_count: int
    between_pair_count: int
    permutations: int
    p_value: float | None
    distinct_groupings: int
    min_achievable_p: float
    design_has_resolution: bool
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class CollapseReport:
    candidate_count: int
    profile_count: int
    profiles_with_replicates: int
    replicates_available: bool
    mean_pairwise_distance: float
    min_pairwise_distance: float
    max_pairwise_distance: float
    duplicate_pairs: list[tuple[str, str, float]] = field(default_factory=list)
    separations: list[ProfileSeparation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["duplicate_pairs"] = [list(pair) for pair in self.duplicate_pairs]
        return payload


def distinct_groupings(labels: Sequence[str]) -> int:
    """Number of distinct labeled assignments with these profile-group sizes."""

    sizes: dict[str, int] = {}
    for label in labels:
        sizes[label] = sizes.get(label, 0) + 1
    total = factorial(len(labels))
    for size in sizes.values():
        total //= factorial(size)
    return total


def permutation_resolution(labels: Sequence[str]) -> tuple[int, float]:
    """Return (distinct groupings, smallest reachable p-value).

    Relabeling equal-sized groups produces the same partition and therefore the
    exact same separation ratio, so those permutations always tie with the
    observed value. The floor is that tie count over the number of groupings.

    Three profiles of two samples each gives 3!/90 = 0.067: no p-value below
    that is reachable however large the real effect is. Five profiles of two
    reaches 5!/113400 = 0.001, which is ample.
    """

    sizes: dict[str, int] = {}
    for label in labels:
        sizes[label] = sizes.get(label, 0) + 1

    groups_per_size: dict[int, int] = {}
    for size in sizes.values():
        groups_per_size[size] = groups_per_size.get(size, 0) + 1

    ties = 1
    for count in groups_per_size.values():
        ties *= factorial(count)

    groupings = distinct_groupings(labels)
    return groupings, ties / groupings


def _interpret(ratio: float, p_value: float | None, *, design_has_resolution: bool) -> str:
    # Only let the p-value veto when the design could actually have produced a
    # small one. Otherwise a large real effect gets labeled collapsed purely
    # because too few candidates were generated.
    if design_has_resolution and p_value is not None and p_value > 0.10:
        return (
            "collapsed: profile labels explain no more dispersion than a random "
            "regrouping of the same candidates"
        )
    if not design_has_resolution and ratio >= 1.25:
        return (
            "separated (underpowered): dispersion favors the profiles, but too few "
            "candidates exist for the permutation test to confirm it; add samples "
            "per profile"
        )
    if ratio < 1.05:
        return (
            "collapsed: between-profile dispersion does not exceed within-profile "
            "dispersion"
        )
    if ratio < 1.25:
        return "weak: profiles shift the output only slightly beyond sampling noise"
    return "separated: profiles move candidates beyond within-profile sampling noise"


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _separation(
    labels: Sequence[str],
    matrix: list[list[float]],
) -> tuple[float, float, int, int]:
    """Return (within mean, between mean, within pairs, between pairs)."""

    within: list[float] = []
    between: list[float] = []
    for i, j in combinations(range(len(labels)), 2):
        if labels[i] == labels[j]:
            within.append(matrix[i][j])
        else:
            between.append(matrix[i][j])
    return _mean(within), _mean(between), len(within), len(between)


def analyze_profile_separation(
    candidates: Sequence[tuple[str, str, str]],
    *,
    distance_mode: DistanceMode = STYLISTIC,
    permutations: int = 2000,
    seed: int = 12345,
) -> ProfileSeparation:
    """Compare between-profile and within-profile dispersion.

    ``candidates`` is a sequence of ``(candidate_id, profile, text)``. At least
    one profile must contribute two or more candidates, otherwise there is no
    within-profile term and the comparison is undefined.

    The permutation test reshuffles the profile labels across the same fixed
    distance matrix, so it asks exactly the right question: could this apparent
    profile effect have arisen from grouping these candidates arbitrarily? It is
    deterministic for a given ``seed``.
    """

    if len(candidates) < 3:
        raise ValueError("profile separation requires at least three candidates")

    labels = [profile for _, profile, _ in candidates]
    texts = [text for _, _, text in candidates]
    if len(set(labels)) < 2:
        raise ValueError("profile separation requires at least two distinct profiles")
    if len(set(labels)) == len(labels):
        raise ValueError(
            "profile separation requires replicates: every profile has exactly one "
            "candidate, so within-profile dispersion is undefined"
        )

    distance = _distance_for_mode(distance_mode)
    count = len(texts)
    matrix = [[0.0] * count for _ in range(count)]
    for i in range(count):
        for j in range(i + 1, count):
            value = distance(texts[i], texts[j])
            matrix[i][j] = value
            matrix[j][i] = value

    within_mean, between_mean, within_pairs, between_pairs = _separation(labels, matrix)
    ratio = between_mean / within_mean if within_mean > 0 else float("inf")

    p_value: float | None = None
    if permutations > 0 and within_pairs and between_pairs:
        rng = random.Random(seed)
        shuffled = list(labels)
        at_least_as_extreme = 0
        for _ in range(permutations):
            rng.shuffle(shuffled)
            perm_within, perm_between, perm_w, perm_b = _separation(shuffled, matrix)
            if not perm_w or not perm_b:
                continue
            perm_ratio = perm_between / perm_within if perm_within > 0 else float("inf")
            if perm_ratio >= ratio:
                at_least_as_extreme += 1
        # Add-one correction keeps the p-value away from an unattainable zero.
        p_value = (at_least_as_extreme + 1) / (permutations + 1)

    groupings, min_achievable_p = permutation_resolution(labels)
    design_has_resolution = min_achievable_p <= 0.05

    return ProfileSeparation(
        distance_mode=distance_mode,
        within_profile_mean=within_mean,
        between_profile_mean=between_mean,
        separation_ratio=ratio,
        within_pair_count=within_pairs,
        between_pair_count=between_pairs,
        permutations=permutations,
        p_value=p_value,
        distinct_groupings=groupings,
        min_achievable_p=min_achievable_p,
        design_has_resolution=design_has_resolution,
        interpretation=_interpret(
            ratio, p_value, design_has_resolution=design_has_resolution
        ),
    )


def assess_collapse(
    candidates: Sequence[tuple[str, str, str]],
    *,
    duplicate_threshold: float = 0.05,
    permutations: int = 2000,
    seed: int = 12345,
) -> CollapseReport:
    """Summarize whether a candidate batch collapsed toward one distribution.

    ``candidates`` is a sequence of ``(candidate_id, profile, text)``.
    """

    if not candidates:
        raise ValueError("assess_collapse requires at least one candidate")

    ids = [cid for cid, _, _ in candidates]
    labels = [profile for _, profile, _ in candidates]
    texts = [text for _, _, text in candidates]
    notes: list[str] = []

    distances: list[float] = []
    duplicate_pairs: list[tuple[str, str, float]] = []
    for i, j in combinations(range(len(texts)), 2):
        value = pair_distance(texts[i], texts[j])
        distances.append(value)
        if value < duplicate_threshold:
            duplicate_pairs.append((ids[i], ids[j], value))

    per_profile: dict[str, int] = {}
    for label in labels:
        per_profile[label] = per_profile.get(label, 0) + 1
    with_replicates = sum(1 for total in per_profile.values() if total >= 2)
    replicates_available = with_replicates > 0

    separations: list[ProfileSeparation] = []
    if not replicates_available:
        notes.append(
            "no profile has two or more candidates, so within-profile dispersion is "
            "undefined and profile effects cannot be separated from sampling noise; "
            "regenerate the batch with at least two samples per profile"
        )
    elif len(per_profile) < 2:
        notes.append("only one profile is present, so between-profile dispersion is undefined")
    elif len(candidates) < 3:
        notes.append("fewer than three candidates; profile separation was not computed")
    else:
        for mode in (STYLISTIC, COMPOSITE):
            separations.append(
                analyze_profile_separation(
                    candidates,
                    distance_mode=mode,
                    permutations=permutations,
                    seed=seed,
                )
            )
        if separations and not separations[0].design_has_resolution:
            notes.append(
                "underpowered design: only "
                f"{separations[0].distinct_groupings} distinct profile groupings exist, "
                f"so no p-value below {separations[0].min_achievable_p:.3f} is reachable "
                "regardless of effect size; add profiles or samples per profile"
            )

    if duplicate_pairs:
        notes.append(
            f"{len(duplicate_pairs)} near-duplicate pair(s) below {duplicate_threshold:.3f}"
        )

    return CollapseReport(
        candidate_count=len(candidates),
        profile_count=len(per_profile),
        profiles_with_replicates=with_replicates,
        replicates_available=replicates_available,
        mean_pairwise_distance=_mean(distances),
        min_pairwise_distance=min(distances) if distances else 0.0,
        max_pairwise_distance=max(distances) if distances else 0.0,
        duplicate_pairs=duplicate_pairs,
        separations=separations,
        notes=notes,
    )
