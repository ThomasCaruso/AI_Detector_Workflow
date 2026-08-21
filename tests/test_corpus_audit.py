from authorship_shift.corpus_audit import audit_corpus, genre_split_coverage
from authorship_shift.lora_data import LoraExample, Provenance


def _example(
    example_id: str,
    *,
    source_id: str,
    split: str = "train",
    genre: str = "science_summary",
    text: str | None = None,
):
    return LoraExample(
        id=example_id,
        genre=genre,
        split=split,
        instruction="Explain the result.",
        content_atoms=("one fact", "one qualification"),
        immutable_details=(),
        required_qualifications=(),
        target_text=text
        or (
            "The measurements remained stable through the first interval, while the second "
            "site changed later in the season. The report describes the difference without "
            "claiming that the observed timing established a cause."
        ),
        provenance=Provenance(
            kind="public_domain",
            source_id=source_id,
            license="Public Domain (U.S. Government work)",
        ),
    )


def test_audit_reports_balance_and_source_concentration():
    rows = [
        _example("a", source_id="s1"),
        _example("b", source_id="s1", text="A second unrelated paragraph discusses a different measured pattern and its limits."),
        _example("c", source_id="s2", genre="business_analysis", text="The analysis separates recurring revenue from a temporary contribution and keeps the scenario assumptions explicit."),
    ]
    report = audit_corpus(rows, max_source_share=0.50, min_genre_examples=2)
    assert report.example_count == 3
    assert report.examples_by_source["s1"] == 2
    assert report.largest_source_example_share == 2 / 3
    assert any("largest source" in warning for warning in report.warnings)
    assert any("business_analysis" in warning for warning in report.warnings)


def test_audit_flags_cross_split_near_duplicate_targets():
    base = (
        "Measurements taken over several seasons showed a persistent difference between the "
        "two sites, although the observational design did not establish the cause. The report "
        "separates the measured pattern from the mechanisms that might explain it."
    )
    almost_same = (
        "Measurements taken over several seasons showed a persistent difference between the "
        "two sites, although the observational design did not establish the cause. The report "
        "separates the measured pattern from mechanisms that might explain it."
    )
    rows = [
        _example("a", source_id="s1", split="train", text=base),
        _example("b", source_id="s2", split="holdout", text=almost_same),
    ]
    report = audit_corpus(rows, near_duplicate_threshold=0.70, max_source_share=1.0, min_genre_examples=1)
    assert len(report.near_duplicates) == 1
    pair = report.near_duplicates[0]
    assert {pair.left_split, pair.right_split} == {"train", "holdout"}
    assert any("cross train/dev/holdout" in warning for warning in report.warnings)


def test_audit_does_not_flag_unrelated_targets():
    rows = [
        _example("a", source_id="s1", text="A long technical explanation describes retries, latency, timeout behavior, and the sequence of an outage without claiming permanent loss."),
        _example("b", source_id="s2", text="An investment paragraph discusses revenue quality, normalized earnings, leverage, and scenario assumptions under a proposed valuation."),
    ]
    report = audit_corpus(rows, near_duplicate_threshold=0.50, max_source_share=1.0, min_genre_examples=1)
    assert report.near_duplicates == []


def test_genre_split_coverage_reports_missing_cells_and_source_counts():
    rows = [
        _example("s-train", source_id="science-train", split="train"),
        _example("s-dev", source_id="science-dev", split="dev"),
        _example("s-hold", source_id="science-hold", split="holdout"),
        _example("b-train", source_id="business-train", split="train", genre="business_analysis"),
    ]
    examples, sources, missing = genre_split_coverage(
        rows,
        expected_genres=("science_summary", "business_analysis"),
    )
    assert examples["science_summary"] == {"train": 1, "dev": 1, "holdout": 1}
    assert sources["science_summary"] == {"train": 1, "dev": 1, "holdout": 1}
    assert "business_analysis:dev" in missing
    assert "business_analysis:holdout" in missing


def test_audit_marks_complete_genre_split_matrix():
    rows = []
    for genre in ("science_summary", "business_analysis"):
        for split in ("train", "dev", "holdout"):
            rows.append(
                _example(
                    f"{genre}-{split}",
                    source_id=f"{genre}-{split}-source",
                    split=split,
                    genre=genre,
                    text=f"A distinct {genre} paragraph for {split} contains enough prose to audit the split matrix without reusing target text.",
                )
            )
    report = audit_corpus(
        rows,
        max_source_share=1.0,
        min_genre_examples=1,
        expected_genres=("science_summary", "business_analysis"),
    )
    assert report.genre_split_coverage_ok is True
    assert report.missing_genre_splits == []


def test_audit_marks_entirely_missing_expected_genre():
    rows = [
        _example("s-train", source_id="science-train", split="train"),
        _example("s-dev", source_id="science-dev", split="dev"),
        _example("s-hold", source_id="science-hold", split="holdout"),
    ]
    report = audit_corpus(
        rows,
        max_source_share=1.0,
        min_genre_examples=1,
        expected_genres=("science_summary", "professional_writing"),
    )
    assert report.genre_split_coverage_ok is False
    assert {
        "professional_writing:train",
        "professional_writing:dev",
        "professional_writing:holdout",
    }.issubset(set(report.missing_genre_splits))
