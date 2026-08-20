from __future__ import annotations

from .engine_v2 import GenerationControls, GenerationProfile


def default_generation_profiles(*, base_seed: int = 100) -> list[GenerationProfile]:
    """Return a small, reproducible profile set for Engine v2 experiments.

    The profiles vary discourse organization while keeping the core assignment
    unchanged. Sampling controls are requests to the provider, not guarantees.
    """

    return [
        GenerationProfile(
            name="direct-plain",
            directive=(
                "Use plain analytical prose. Start with the most concrete statement that "
                "helps the reader understand the subject. Avoid an essay-style preview of "
                "the points that follow."
            ),
            controls=GenerationControls(
                temperature=0.65,
                top_p=0.95,
                seed=base_seed,
            ),
        ),
        GenerationProfile(
            name="mechanism-first",
            directive=(
                "Begin with the mechanism or action that makes the conclusion true. Name "
                "the broader conclusion only after the mechanism is visible."
            ),
            controls=GenerationControls(
                temperature=0.85,
                top_p=0.95,
                seed=base_seed + 100,
            ),
        ),
        GenerationProfile(
            name="constraint-first",
            directive=(
                "Open with the most important limitation, tradeoff, or constraint, then "
                "show how the main claim survives or changes under that constraint."
            ),
            controls=GenerationControls(
                temperature=0.9,
                top_p=0.92,
                seed=base_seed + 200,
            ),
        ),
        GenerationProfile(
            name="evidence-first",
            directive=(
                "Lead with the strongest concrete fact, example, or observable consequence. "
                "Let interpretation follow instead of announcing the thesis first."
            ),
            controls=GenerationControls(
                temperature=0.8,
                top_p=0.9,
                seed=base_seed + 300,
            ),
        ),
        GenerationProfile(
            name="compressed-asymmetric",
            directive=(
                "Compress obvious background and spend more space on the most consequential "
                "or uncertain part of the reasoning. Do not give each requested point equal "
                "sentence space merely because the prompt lists them evenly."
            ),
            controls=GenerationControls(
                temperature=1.0,
                top_p=0.95,
                seed=base_seed + 400,
            ),
        ),
    ]
