from authorship_shift.candidate_lab import (
    analyze_candidates,
    immutable_coverage,
    opening_repeat_ratio,
    source_ngram_overlap,
)
from authorship_shift.engine_v2 import (
    GenerationControls,
    GenerationProfile,
    generate_candidate_batch,
)


class FakeGenerator:
    identity = "fake-controlled"

    def __init__(self):
        self.calls = []

    def generate(self, *, source, content_atoms, directive, controls):
        self.calls.append(
            {
                "source": source,
                "content_atoms": list(content_atoms),
                "directive": directive,
                "controls": controls,
            }
        )
        seed = controls.seed if controls.seed is not None else 0
        return (
            f"Northstar grew 27% in 2025. Candidate seed {seed} changes the sentence shape. "
            "Managers still preserve the stated qualification."
        )


def test_candidate_lab_detects_immutable_loss_and_overlap():
    source = "Northstar grew 27% in 2025 after a limited pilot."
    good = "Northstar grew 27% in 2025, although the pilot remained limited."
    bad = "The company grew after a pilot."

    coverage, missing = immutable_coverage(source, good)
    assert coverage == 1.0
    assert missing == []

    bad_coverage, bad_missing = immutable_coverage(source, bad)
    assert bad_coverage < 1.0
    assert "27%" in bad_missing
    assert "2025" in bad_missing

    assert source_ngram_overlap(source, good) > source_ngram_overlap(source, bad)


def test_candidate_lab_measures_opening_repetition_and_pair_distance():
    repeated = "However, costs rose. However, margins fell. However, demand slowed."
    varied = "Costs rose. Margins fell afterward. Demand then slowed."
    assert opening_repeat_ratio(repeated) > opening_repeat_ratio(varied)

    analyses = analyze_candidates(
        "Costs changed during the period.",
        [("a", repeated), ("b", varied)],
    )
    assert len(analyses) == 2
    assert all(row.mean_pairwise_distance > 0 for row in analyses)


def test_engine_generates_independent_candidates_and_increments_seed():
    generator = FakeGenerator()
    profiles = [
        GenerationProfile(
            name="mechanism-first",
            directive="Begin from the mechanism.",
            controls=GenerationControls(temperature=0.8, top_p=0.95, seed=40),
        ),
        GenerationProfile(
            name="constraint-first",
            directive="Begin from the limiting condition.",
            controls=GenerationControls(temperature=1.0, top_p=0.9, seed=80),
        ),
    ]

    run = generate_candidate_batch(
        source="Northstar grew 27% in 2025.",
        content_atoms=["Northstar", "27% growth", "2025"],
        generator=generator,
        profiles=profiles,
        candidates_per_profile=2,
    )

    assert len(run.candidates) == 4
    assert [c.controls["seed"] for c in run.candidates] == [40, 41, 80, 81]
    assert all(c.analysis is not None for c in run.candidates)
    assert all(c.analysis.immutable_coverage == 1.0 for c in run.candidates)
    assert generator.calls[0]["content_atoms"] == ["Northstar", "27% growth", "2025"]


def test_engine_rejects_invalid_batches():
    generator = FakeGenerator()
    profile = GenerationProfile(name="default")

    try:
        generate_candidate_batch(
            source="",
            content_atoms=["fact"],
            generator=generator,
            profiles=[profile],
        )
    except ValueError as exc:
        assert "source" in str(exc)
    else:
        raise AssertionError("empty source should fail")
