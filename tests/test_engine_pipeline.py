"""End-to-end coverage of the zero-API Engine v2 chain.

Exercises generation, deterministic diagnostics, batch gating, collapse
diagnostics, and reranking together through the replay provider, so the
five-profile experiment is verified from a fresh checkout without any API call.
"""

from authorship_shift.batch_gate import assess_batch
from authorship_shift.collapse import assess_collapse
from authorship_shift.engine_v2 import generate_candidate_batch
from authorship_shift.generation_profiles import default_generation_profiles
from authorship_shift.providers.replay import ReplayGenerator
from authorship_shift.rerank import rerank

SOURCE = (
    "Northstar Mobility reported $18.4 million of revenue in 2025 and grew 27% "
    "year over year. Roughly 9 percentage points of that growth came from a "
    "rebate program that ends in December 2025."
)

ATOMS = [
    "part of the growth came from a one-time rebate",
    "the rebate program ends in December 2025",
]

# Ten candidates: five profiles, two samples each. Every candidate preserves the
# literal details, and the wording varies enough to avoid a collapsed batch.
_OPENINGS = [
    "Northstar Mobility booked $18.4 million of revenue in 2025",
    "Revenue at Northstar Mobility reached $18.4 million during 2025",
    "In 2025 Northstar Mobility recorded $18.4 million of revenue",
    "The 2025 books at Northstar Mobility show $18.4 million of revenue",
    "Northstar Mobility closed 2025 holding $18.4 million of revenue",
    "For 2025, Northstar Mobility posted revenue of $18.4 million",
    "Across 2025 Northstar Mobility took in $18.4 million of revenue",
    "Northstar Mobility ended 2025 with $18.4 million of revenue",
    "Revenue of $18.4 million landed at Northstar Mobility in 2025",
    "Northstar Mobility's 2025 revenue came to $18.4 million",
]

_MIDDLES = [
    "against growth of 27% year over year.",
    "on year-over-year growth of 27%.",
    "with the top line up 27% from the prior year.",
    "as growth registered 27% over the comparable period.",
    "while growth of 27% carried the comparison.",
    "and growth of 27% framed the result.",
    "alongside a 27% year-over-year gain.",
    "with 27% growth relative to last year.",
    "as the year-over-year figure hit 27%.",
    "and the annual comparison showed 27%.",
]

_TAILS = [
    "Roughly 9 percentage points of that came from a rebate program ending in December 2025.",
    "A rebate program closing in December 2025 supplied about 9 percentage points of it.",
    "About 9 percentage points traced to a rebate program that stops in December 2025.",
    "Some 9 percentage points depended on a rebate program expiring in December 2025.",
    "Nearly 9 percentage points rested on a rebate program due to end in December 2025.",
    "Of that, 9 percentage points or so came from a rebate program ending December 2025.",
    "A December 2025 rebate program accounted for approximately 9 percentage points.",
    "Around 9 percentage points arrived through a rebate program lapsing in December 2025.",
    "The rebate program winding down in December 2025 gave about 9 percentage points.",
    "Close to 9 percentage points followed from a rebate program that ends December 2025.",
]

CANDIDATES = [
    f"{opening} {middle} {tail} The distinction matters for any forward view."
    for opening, middle, tail in zip(_OPENINGS, _MIDDLES, _TAILS)
]


def _run():
    generator = ReplayGenerator(CANDIDATES, identity="replay-test")
    return generate_candidate_batch(
        source=SOURCE,
        content_atoms=ATOMS,
        generator=generator,
        profiles=default_generation_profiles(),
        candidates_per_profile=2,
    )


def test_five_profile_two_sample_batch_runs_end_to_end():
    run = _run()

    assert len(run.candidates) == 10
    assert [c.profile for c in run.candidates[:2]] == ["direct-plain", "direct-plain"]
    assert [c.controls["seed"] for c in run.candidates[:2]] == [100, 101]
    assert all(c.analysis is not None for c in run.candidates)

    payload = run.to_dict()
    assert len(payload["candidates"]) == 10
    assert payload["candidates"][0]["analysis"]["immutable_count"] > 0


def test_batch_gate_sees_real_fidelity_evidence():
    run = _run()
    analyses = [c.analysis for c in run.candidates]
    gate = assess_batch(analyses, target_words=len(CANDIDATES[0].split()))

    assert gate.fidelity_evidence == "checked"
    assert all(row.immutable_coverage == 1.0 for row in analyses)
    assert gate.min_nearest_neighbor_distance > 0


def test_collapse_analysis_is_powered_by_the_five_by_two_design():
    run = _run()
    report = assess_collapse(
        [(c.id, c.profile, c.text) for c in run.candidates],
        permutations=300,
    )

    assert report.replicates_available is True
    assert report.profiles_with_replicates == 5
    assert report.separations
    # 5 profiles x 2 samples resolves far below 0.05, unlike a 3x2 design.
    assert all(row.design_has_resolution for row in report.separations)
    assert not any("underpowered" in note for note in report.notes)


def test_rerank_shortlists_from_the_generated_batch():
    run = _run()
    result = rerank(
        [(c.id, c.text) for c in run.candidates],
        [c.analysis for c in run.candidates],
        select=3,
    )

    assert len(result.selected) == 3
    assert len(set(result.selected)) == 3
    assert result.eligible_count == 10
    assert all(cid in {c.id for c in run.candidates} for cid in result.selected)
