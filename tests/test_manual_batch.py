"""Tests for manual batch preparation and loading."""

import json

import pytest

from authorship_shift.manual_batch import (
    MANIFEST_SCHEMA_VERSION,
    load_all_cases,
    load_batch,
    load_case,
    manifest_candidates,
    prepare_batch,
    render_prompt,
    sample_controls,
)
from authorship_shift.engine_v2 import GenerationControls

CASE = {
    "id": "demo_001",
    "genre": "business_analysis",
    "target_words": 300,
    "source": "Acme Holdings grew 27% in 2025 after a limited rebate program.",
    "task": "Explain the result.",
    "required_qualifications": ["the rebate program was limited"],
}


def test_prepare_batch_single_sample_keeps_v1_filenames(tmp_path):
    manifest = prepare_batch(CASE, tmp_path, samples_per_profile=1)

    assert manifest["schema_version"] == MANIFEST_SCHEMA_VERSION
    assert len(manifest["candidates"]) == 5
    assert (tmp_path / "prompts" / "01_direct-plain.md").exists()
    assert manifest["candidates"][0]["expected_output_file"] == "outputs/01_direct-plain.txt"
    assert (tmp_path / "outputs").is_dir()
    assert "one sample per profile" in (tmp_path / "README.md").read_text(encoding="utf-8")


def test_prepare_batch_replicates_offset_seeds_like_the_engine(tmp_path):
    manifest = prepare_batch(CASE, tmp_path, samples_per_profile=2)

    assert len(manifest["candidates"]) == 10
    assert (tmp_path / "prompts" / "01_direct-plain_c1.md").exists()
    assert (tmp_path / "prompts" / "01_direct-plain_c2.md").exists()

    first, second = manifest["candidates"][0], manifest["candidates"][1]
    assert first["candidate_id"] == "p1-c1"
    assert second["candidate_id"] == "p1-c2"
    assert second["requested_controls"]["seed"] == first["requested_controls"]["seed"] + 1
    assert "independent samples per profile" in (tmp_path / "README.md").read_text(
        encoding="utf-8"
    )


def test_prepare_batch_rejects_zero_samples(tmp_path):
    with pytest.raises(ValueError, match="samples_per_profile"):
        prepare_batch(CASE, tmp_path, samples_per_profile=0)


def test_sample_controls_leaves_the_first_sample_alone():
    controls = GenerationControls(temperature=0.8, top_p=0.9, seed=100, max_tokens=512)
    assert sample_controls(controls, 0) is controls
    assert sample_controls(controls, 3).seed == 103
    assert sample_controls(GenerationControls(seed=None), 2).seed is None


def test_render_prompt_carries_the_locked_material():
    text = render_prompt(CASE, "mechanism-first", "Begin from the mechanism.")

    assert CASE["source"] in text
    assert CASE["task"] in text
    assert "Begin from the mechanism." in text
    assert "the rebate program was limited" in text
    assert "approximately 300 words" in text


def test_render_prompt_requires_named_entities_to_be_named():
    """Both constraint-first pilot candidates dropped the company name entirely.

    The requirement is constant across every profile, so it cannot bias the
    within-profile term against the between-profile term.
    """

    text = render_prompt(CASE, "constraint-first", "Open with the constraint.")
    assert "use that exact name at least once" in text
    assert 'referring to it only as "the company"' in text


def test_render_prompt_forbids_inventing_a_name():
    """An unconditional naming demand made the model fabricate a subject.

    technical_postmortem_001 names no organization, so the earlier wording sent
    the model to the only proper noun in view -- the prompt's own document
    header -- and it reported the outage as having happened to AuthorshipShift.
    The requirement must be conditional on the locked facts naming someone.
    """

    text = render_prompt(CASE, "direct-plain", "Be plain.")
    assert "Do not introduce any name that does not appear in the locked facts" in text
    assert "if the locked facts name nobody, do not invent a name" in text


def test_render_prompt_without_a_target_length():
    case = dict(CASE)
    case.pop("target_words")
    assert "Use the length required by the task." in render_prompt(case, "p", "d")


def test_load_batch_reports_missing_outputs(tmp_path):
    manifest = prepare_batch(CASE, tmp_path, samples_per_profile=2)
    filled = manifest["candidates"][:3]
    for index, entry in enumerate(filled):
        (tmp_path / entry["expected_output_file"]).write_text(
            f"Acme Holdings grew 27% in 2025. Variation number {index}.",
            encoding="utf-8",
        )

    batch = load_batch(tmp_path)
    assert len(batch.candidates) == 3
    assert len(batch.missing) == 7
    assert batch.expected_count == 10
    assert batch.complete is False
    assert batch.case_id == "demo_001"
    assert batch.genre == "business_analysis"
    assert batch.target_words == 300


def test_load_batch_treats_whitespace_only_output_as_missing(tmp_path):
    manifest = prepare_batch(CASE, tmp_path, samples_per_profile=1)
    (tmp_path / manifest["candidates"][0]["expected_output_file"]).write_text(
        "   \n  ", encoding="utf-8"
    )

    batch = load_batch(tmp_path)
    assert batch.candidates == []
    assert len(batch.missing) == 5


def test_load_batch_adapts_a_v1_manifest(tmp_path):
    """Batches prepared before replicate support must still load."""

    v1 = {
        "case_id": "legacy_001",
        "genre": "science_summary",
        "target_words": 280,
        "source": CASE["source"],
        "task": CASE["task"],
        "profiles": [
            {
                "index": 1,
                "name": "direct-plain",
                "prompt_file": "prompts/01_direct-plain.md",
                "expected_output_file": "outputs/01_direct-plain.txt",
                "requested_controls": {"seed": 100},
            }
        ],
    }
    (tmp_path / "outputs").mkdir()
    (tmp_path / "manifest.json").write_text(json.dumps(v1), encoding="utf-8")
    (tmp_path / "outputs" / "01_direct-plain.txt").write_text("Legacy prose.", encoding="utf-8")

    entries = manifest_candidates(v1)
    assert entries[0]["candidate_id"] == "direct-plain"
    assert entries[0]["sample_index"] == 1

    batch = load_batch(tmp_path)
    assert batch.candidates == [("direct-plain", "Legacy prose.")]
    assert batch.labeled == [("direct-plain", "direct-plain", "Legacy prose.")]
    assert batch.complete is True


def test_load_batch_rejects_duplicate_candidate_ids(tmp_path):
    manifest = prepare_batch(CASE, tmp_path, samples_per_profile=1)
    manifest["candidates"][1]["candidate_id"] = manifest["candidates"][0]["candidate_id"]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate candidate id"):
        load_batch(tmp_path)


def test_load_batch_requires_a_manifest(tmp_path):
    with pytest.raises(FileNotFoundError, match="manifest.json"):
        load_batch(tmp_path)


def test_load_case_and_load_all_cases_use_the_real_corpus():
    from pathlib import Path

    corpus = Path(__file__).resolve().parents[1] / "evals" / "engine_v2_seed_cases.json"
    cases = load_all_cases(corpus)
    assert len(cases) == 5

    case = load_case(corpus, "science_summary_001")
    assert case["genre"] == "science_summary"

    with pytest.raises(ValueError, match="not found"):
        load_case(corpus, "no_such_case")
