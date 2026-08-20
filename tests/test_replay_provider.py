from pathlib import Path

import pytest

from authorship_shift.engine_v2 import GenerationControls
from authorship_shift.providers.replay import ReplayGenerator


def test_replay_generator_consumes_responses_in_order():
    generator = ReplayGenerator(["first candidate", "second candidate"])
    controls = GenerationControls(seed=7)

    first = generator.generate(
        source="source",
        content_atoms=["fact"],
        directive="profile A",
        controls=controls,
    )
    second = generator.generate(
        source="source",
        content_atoms=["fact"],
        directive="profile B",
        controls=controls,
    )

    assert first == "first candidate"
    assert second == "second candidate"
    assert generator.remaining == 0
    assert generator.calls[0]["controls"]["seed"] == 7

    with pytest.raises(RuntimeError):
        generator.generate(
            source="source",
            content_atoms=["fact"],
            directive="extra",
            controls=controls,
        )


def test_replay_generator_loads_sorted_text_files(tmp_path: Path):
    (tmp_path / "b.txt").write_text("second", encoding="utf-8")
    (tmp_path / "a.txt").write_text("first", encoding="utf-8")

    generator = ReplayGenerator.from_directory(tmp_path)
    controls = GenerationControls()

    assert generator.generate(
        source="source",
        content_atoms=["fact"],
        directive="",
        controls=controls,
    ) == "first"
    assert generator.generate(
        source="source",
        content_atoms=["fact"],
        directive="",
        controls=controls,
    ) == "second"


def test_replay_generator_rejects_empty_inputs(tmp_path: Path):
    with pytest.raises(ValueError):
        ReplayGenerator([])

    with pytest.raises(ValueError):
        ReplayGenerator.from_directory(tmp_path)
