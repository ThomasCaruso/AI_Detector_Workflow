from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Protocol, Sequence

from .candidate_lab import CandidateAnalysis, analyze_candidates


@dataclass(frozen=True)
class GenerationControls:
    """Provider-facing generation controls.

    Providers may support all, some, or none of these fields. The engine records
    the requested controls even when a concrete provider cannot honor them.
    """

    temperature: float | None = None
    top_p: float | None = None
    seed: int | None = None
    max_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class GenerationProfile:
    name: str
    directive: str = ""
    controls: GenerationControls = field(default_factory=GenerationControls)


@dataclass
class GeneratedCandidate:
    id: str
    text: str
    profile: str
    generator: str
    controls: dict[str, Any]
    analysis: CandidateAnalysis | None = None


class ControlledGenerator(Protocol):
    """Minimal generation interface for the v2 engine.

    Implementations can wrap hosted APIs, open-weight models, local inference,
    tuned adapters, or a manual/offline bridge. AuthorshipShift does not require
    any single provider.
    """

    @property
    def identity(self) -> str:
        ...

    def generate(
        self,
        *,
        source: str,
        content_atoms: Sequence[str],
        directive: str,
        controls: GenerationControls,
    ) -> str:
        ...


@dataclass
class EngineRun:
    source: str
    content_atoms: list[str]
    candidates: list[GeneratedCandidate]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "content_atoms": list(self.content_atoms),
            "candidates": [
                {
                    "id": candidate.id,
                    "text": candidate.text,
                    "profile": candidate.profile,
                    "generator": candidate.generator,
                    "controls": candidate.controls,
                    "analysis": candidate.analysis.to_dict() if candidate.analysis else None,
                }
                for candidate in self.candidates
            ],
        }


def generate_candidate_batch(
    *,
    source: str,
    content_atoms: Sequence[str],
    generator: ControlledGenerator,
    profiles: Sequence[GenerationProfile],
    candidates_per_profile: int = 1,
) -> EngineRun:
    """Generate independent candidates, then attach deterministic diagnostics.

    This deliberately separates generation from selection. A provider that can
    honor sampling controls can create genuinely different trajectories; a
    manual or deterministic provider can still participate for development and
    regression testing.
    """

    if not source.strip():
        raise ValueError("source must not be empty")
    if not content_atoms:
        raise ValueError("content_atoms must not be empty")
    if not profiles:
        raise ValueError("at least one generation profile is required")
    if candidates_per_profile < 1:
        raise ValueError("candidates_per_profile must be >= 1")

    generated: list[GeneratedCandidate] = []
    for profile_index, profile in enumerate(profiles):
        for sample_index in range(candidates_per_profile):
            controls = profile.controls
            if controls.seed is not None and candidates_per_profile > 1:
                controls = GenerationControls(
                    temperature=controls.temperature,
                    top_p=controls.top_p,
                    seed=controls.seed + sample_index,
                    max_tokens=controls.max_tokens,
                )
            text = generator.generate(
                source=source,
                content_atoms=content_atoms,
                directive=profile.directive,
                controls=controls,
            )
            if not text.strip():
                raise RuntimeError(
                    f"generator {generator.identity!r} returned an empty candidate"
                )
            generated.append(
                GeneratedCandidate(
                    id=f"p{profile_index + 1}-c{sample_index + 1}",
                    text=text.strip(),
                    profile=profile.name,
                    generator=generator.identity,
                    controls=controls.to_dict(),
                )
            )

    analyses = analyze_candidates(
        source,
        [(candidate.id, candidate.text) for candidate in generated],
    )
    by_id = {analysis.candidate_id: analysis for analysis in analyses}
    for candidate in generated:
        candidate.analysis = by_id[candidate.id]

    return EngineRun(
        source=source,
        content_atoms=list(content_atoms),
        candidates=generated,
    )
