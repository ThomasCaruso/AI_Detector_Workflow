"""Tests for personal-corpus target selection, unit grouping, and annotation gates.

Every fixture here is synthetic prose. The suite never reads the gitignored
personal corpus.
"""

from __future__ import annotations

import pytest

from authorship_shift.personal_extraction import Region
from authorship_shift.personal_targets import (
    QUOTATION_SELF,
    QUOTATION_TITLE,
    REASON_BARE_URL,
    REASON_FROZEN_EXCLUSION,
    REASON_HEADING_STYLE,
    REASON_HOLDOUT,
    REASON_NON_BODY,
    REASON_TABLE,
    AnnotationRecord,
    audit_target_quotations,
    check_plan_fidelity,
    classify_regions,
    find_long_quotations,
    group_target_units,
    run_leakage_checks,
    unit_length_summary,
)


def _region(
    index: int,
    text: str,
    *,
    part: str = "body",
    style: str | None = None,
    in_table: bool = False,
    source_id: str = "essay",
) -> Region:
    return Region(
        region_id=f"{source_id}:b{index:04d}",
        block_index=index,
        part=part,
        style=style,
        in_table=in_table,
        text=text,
    )


def _words(count: int, seed: str = "word") -> str:
    return " ".join(f"{seed}{i}" for i in range(count))


# ---------------------------------------------------------------------------
# Region eligibility
# ---------------------------------------------------------------------------


def test_structural_ineligibility_is_applied_mechanically() -> None:
    regions = [
        _region(0, "Ordinary body prose."),
        _region(1, "Whitlock 3", part="header_footer"),
        _region(2, "Reviewer wants more detail.", part="comment"),
        _region(3, "680", in_table=True),
        _region(4, "A Section Heading", style="Heading2"),
        _region(5, "https://example.org/article?id=7"),
    ]

    verdicts = classify_regions(regions)

    assert [v.reason for v in verdicts] == [
        None,
        REASON_NON_BODY,
        REASON_NON_BODY,
        REASON_TABLE,
        REASON_HEADING_STYLE,
        REASON_BARE_URL,
    ]
    assert [v.eligible for v in verdicts] == [True, False, False, False, False, False]


def test_reviewed_judgements_carry_their_own_reason() -> None:
    regions = [
        _region(0, "Dana Whitlock"),
        _region(1, "Whitlock, Dana. On Shared Reading. Fictional Press, 2020."),
        _region(2, "Real prose about the reading."),
    ]

    verdicts = classify_regions(
        regions, reviewed_ineligible={0: "byline", 1: "citation"}
    )

    assert [(v.eligible, v.reason) for v in verdicts] == [
        (False, "byline"),
        (False, "citation"),
        (True, None),
    ]


def test_frozen_exclusion_outranks_a_reviewed_judgement() -> None:
    # A frozen exclusion is corpus-contract level; it must not be relabelled by
    # a later review pass.
    regions = [_region(49, "Reproduced annotation text.")]

    verdicts = classify_regions(
        regions,
        frozen_excluded_block_indices=[49],
        reviewed_ineligible={49: "citation"},
    )

    assert verdicts[0].reason == REASON_FROZEN_EXCLUSION


def test_holdout_document_has_no_eligible_region() -> None:
    regions = [_region(i, f"Paragraph {i} of held-out prose.") for i in range(4)]

    verdicts = classify_regions(regions, document_is_holdout=True)

    assert all(v.ineligible for v in verdicts)
    assert {v.reason for v in verdicts} == {REASON_HOLDOUT}


def test_reviewed_flags_travel_with_the_region() -> None:
    regions = [_region(0, "Prose quoting a peer.")]

    verdicts = classify_regions(
        regions, reviewed_flags={0: ("embedded_other_author_quotation",)}
    )

    assert verdicts[0].eligible
    assert verdicts[0].flags == ("embedded_other_author_quotation",)


def test_url_with_surrounding_prose_is_not_treated_as_metadata() -> None:
    regions = [_region(0, "I found this at https://example.org and it changed my mind.")]

    verdicts = classify_regions(regions)

    assert verdicts[0].eligible


# ---------------------------------------------------------------------------
# Unit grouping
# ---------------------------------------------------------------------------


def test_a_short_run_becomes_one_unit() -> None:
    regions = [_region(0, _words(60)), _region(1, _words(70, "b"))]
    verdicts = classify_regions(regions)

    units = group_target_units(regions, verdicts, source_id="essay")

    assert len(units) == 1
    assert units[0].words == 130
    assert units[0].region_ids == ("essay:b0000", "essay:b0001")


def test_an_ineligible_region_ends_a_run() -> None:
    regions = [
        _region(0, _words(120)),
        _region(1, "Course Goal 2"),
        _region(2, _words(120, "b")),
    ]
    verdicts = classify_regions(regions, reviewed_ineligible={1: "section_heading"})

    units = group_target_units(regions, verdicts, source_id="essay")

    # Never one unit spanning the heading.
    assert [u.region_ids for u in units] == [("essay:b0000",), ("essay:b0002",)]


def test_a_long_run_is_split_at_paragraph_boundaries_only() -> None:
    sizes = [96, 102, 103, 90, 77, 55]
    regions = [_region(i, _words(size, f"s{i}")) for i, size in enumerate(sizes)]
    verdicts = classify_regions(regions)

    units = group_target_units(regions, verdicts, source_id="essay", max_words=300)

    assert len(units) == 2
    assert [u.words for u in units] == [301, 222]
    # Each unit is a whole number of source paragraphs.
    assert [len(u.region_ids) for u in units] == [3, 3]
    assert all(u.words > 0 for u in units)


def test_partitioning_is_deterministic() -> None:
    sizes = [54, 74, 47, 69, 46, 81, 60, 58, 42, 48]
    regions = [_region(i, _words(size, f"s{i}")) for i, size in enumerate(sizes)]
    verdicts = classify_regions(regions)

    first = group_target_units(regions, verdicts, source_id="essay")
    second = group_target_units(regions, verdicts, source_id="essay")

    assert [u.region_ids for u in first] == [u.region_ids for u in second]


def test_an_oversized_single_paragraph_is_kept_whole_and_flagged() -> None:
    regions = [_region(0, _words(492))]
    verdicts = classify_regions(regions)

    units = group_target_units(regions, verdicts, source_id="letter", max_words=300)

    # Splitting would cut a paragraph, so the unit is reported instead.
    assert len(units) == 1
    assert units[0].words == 492
    assert units[0].oversized_single_paragraph


def test_split_before_marks_a_reviewed_rhetorical_boundary() -> None:
    # 4 x 60 words stays inside the 300-word cap, so only the reviewed
    # boundary can cause a split here.
    regions = [_region(i, _words(60, f"s{i}")) for i in range(4)]
    verdicts = classify_regions(regions)

    without = group_target_units(regions, verdicts, source_id="essay")
    with_split = group_target_units(
        regions, verdicts, source_id="essay", split_before_block_indices=[2]
    )

    assert len(without) == 1
    assert [u.region_ids for u in with_split] == [
        ("essay:b0000", "essay:b0001"),
        ("essay:b0002", "essay:b0003"),
    ]


def test_grouped_target_text_joins_paragraphs_without_rewriting_them() -> None:
    regions = [_region(0, "  First one. "), _region(1, "Second’s here.")]
    verdicts = classify_regions(regions)

    units = group_target_units(regions, verdicts, source_id="essay")

    assert units[0].target_text == "  First one. \n\nSecond’s here."


def test_unit_flags_are_unioned_from_member_regions() -> None:
    regions = [_region(0, _words(50)), _region(1, _words(50, "b"))]
    verdicts = classify_regions(
        regions,
        reviewed_flags={0: ("embedded_source_quotation",), 1: ("embedded_source_quotation",)},
    )

    units = group_target_units(regions, verdicts, source_id="essay")

    assert units[0].flags == ("embedded_source_quotation",)


def test_length_summary_reports_median_min_and_max() -> None:
    regions = [_region(0, _words(100)), _region(1, "Heading"), _region(2, _words(300, "b"))]
    verdicts = classify_regions(regions, reviewed_ineligible={1: "section_heading"})
    units = group_target_units(regions, verdicts, source_id="essay")

    summary = unit_length_summary(units)

    assert summary == {"units": 2, "words": 400, "median": 200.0, "min": 100, "max": 300}


def test_length_summary_of_nothing_is_zeroed() -> None:
    assert unit_length_summary([])["units"] == 0


# ---------------------------------------------------------------------------
# Verbatim third-party quotation inside targets
# ---------------------------------------------------------------------------


def test_a_long_quotation_is_found() -> None:
    text = 'She wrote that “access to reading is never evenly shared among the people who need it”.'

    found = find_long_quotations(text)

    assert len(found) == 1
    assert found[0][0] == 13


def test_short_quotations_are_below_the_substantive_threshold() -> None:
    text = 'The term “shared reading” appears in “On Shared Reading” throughout the chapter.'

    assert find_long_quotations(text) == ()


def test_an_apostrophe_is_not_treated_as_a_quote_delimiter() -> None:
    # Treating apostrophes as delimiters matches across ordinary possessives and
    # yields nonsense spans, so they are excluded.
    text = "Whitlock's account of the writer's own reading habits runs for several pages here."

    assert find_long_quotations(text) == ()


def test_quotations_are_reported_longest_first() -> None:
    text = (
        '“one two three four five six seven eight nine” and '
        '“alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu”'
    )

    found = find_long_quotations(text)

    assert [count for count, _ in found] == [12, 9]


def test_an_undeclared_long_quotation_is_unaccounted_for() -> None:
    regions = {
        "essay:b0000": 'He said “the whole of this sentence belongs to somebody else entirely, not me”.'
    }

    findings = audit_target_quotations(regions)

    assert len(findings) == 1
    assert not findings[0].accounted_for
    assert findings[0].disposition is None


@pytest.mark.parametrize("disposition", [QUOTATION_SELF, QUOTATION_TITLE])
def test_a_declared_long_quotation_is_accounted_for(disposition: str) -> None:
    regions = {
        "essay:b0000": 'I wrote “the whole of this sentence belongs to me and nobody else at all”.'
    }

    findings = audit_target_quotations(regions, dispositions={"essay:b0000": disposition})

    assert findings[0].accounted_for


def test_an_unrecognised_disposition_does_not_count_as_accounted_for() -> None:
    regions = {
        "essay:b0000": 'He said “the whole of this sentence belongs to somebody else entirely, not me”.'
    }

    findings = audit_target_quotations(regions, dispositions={"essay:b0000": "probably fine"})

    assert not findings[0].accounted_for


def test_regions_without_long_quotations_produce_no_findings() -> None:
    regions = {"essay:b0000": "Entirely my own prose, with no quotation in it at all."}

    assert audit_target_quotations(regions) == ()


# ---------------------------------------------------------------------------
# Semantic-plan fidelity
# ---------------------------------------------------------------------------

TARGET = (
    "Whitlock argues that a sponsor of literacy gains an advantage from the literacy "
    "they help others acquire. Although access is uneven, she does not claim it is "
    "absent. In my own case my school plays that role, and I paid 4200 dollars for "
    "the classes."
)

GOOD_PLAN = {
    "content_atoms": [
        "A sponsor is defined by the benefit it draws from another's literacy.",
        "Distribution of access is described as unequal rather than missing.",
        "The writer instantiates the model with his own institution.",
        "The return flow is his payment for tuition.",
    ],
    "immutable_details": [
        "the theorist is Whitlock",
        "the writer paid 4200 dollars",
    ],
    "required_qualifications": [
        "access is called uneven rather than absent",
    ],
    "communicative_function": "summarize",
}


def _check(plan, target=TARGET, region_ids=("essay:b0000",), eligible=("essay:b0000",)):
    return check_plan_fidelity(
        example_id="essay#u00",
        plan=plan,
        target_text=target,
        region_ids=region_ids,
        eligible_region_ids=eligible,
    )


def test_a_clean_plan_passes_every_check() -> None:
    report = _check(GOOD_PLAN)

    assert report.passed, [f.detail for f in report.findings]
    assert report.findings == ()


def test_target_drawing_on_an_ineligible_region_fails() -> None:
    report = _check(GOOD_PLAN, region_ids=("essay:b0000", "essay:b0049"))

    assert not report.passed
    assert any(f.check == "target_regions_eligible" for f in report.failures)


def test_a_number_absent_from_the_target_fails() -> None:
    plan = {**GOOD_PLAN, "immutable_details": ["the writer paid 9900 dollars"]}

    report = _check(plan)

    assert any(f.check == "no_new_facts" for f in report.failures)


def test_a_name_absent_from_the_target_fails() -> None:
    plan = {**GOOD_PLAN, "immutable_details": ["the theorist is Ferrante"]}

    report = _check(plan)

    assert any("Ferrante" in f.detail for f in report.failures)


def test_a_sentence_initial_capital_is_not_treated_as_an_introduced_name() -> None:
    plan = {
        **GOOD_PLAN,
        "content_atoms": [
            "Distribution of access is uneven. Sponsorship still yields mutual benefit.",
            "Meanwhile the writer applies the model to himself.",
            "Payment for tuition is the return flow.",
        ],
    }

    report = _check(plan)

    assert report.passed, [f.detail for f in report.findings]


def test_losing_a_hedged_qualification_fails() -> None:
    plan = {**GOOD_PLAN, "required_qualifications": []}

    report = _check(plan)

    assert any(f.check == "qualifications_preserved" for f in report.failures)


def test_reproducing_target_wording_fails() -> None:
    plan = {
        **GOOD_PLAN,
        "content_atoms": [
            "A sponsor of literacy gains an advantage from the literacy they help others acquire.",
            "The writer instantiates the model with his own institution.",
        ],
    }

    report = _check(plan)

    assert any(f.check == "no_surface_wording" for f in report.failures)


def test_immutable_details_may_match_the_target_verbatim() -> None:
    # Check 3 requires immutable details to agree with the target exactly, so
    # matching is the contract working rather than a leak.
    plan = {
        **GOOD_PLAN,
        "immutable_details": [
            "the theorist is Whitlock",
            "the phrase is 'the literacy they help others acquire'",
            "the writer paid 4200 dollars",
        ],
    }

    report = _check(plan)

    assert report.passed, [f.detail for f in report.findings]


def test_an_overlong_immutable_detail_fails() -> None:
    plan = {
        **GOOD_PLAN,
        "immutable_details": ["the passage says " + _words(40, "x")],
    }

    report = _check(plan)

    assert any("word cap for a detail" in f.detail for f in report.failures)


def test_a_thin_plan_warns_rather_than_failing() -> None:
    plan = {
        "content_atoms": ["Sponsorship is discussed.", "The writer applies it."],
        "immutable_details": [],
        "required_qualifications": ["access is called uneven rather than absent"],
        "communicative_function": "summarize",
    }

    report = _check(plan, target=TARGET + " " + _words(400, "filler"))

    assert any(f.check == "claims_represented" for f in report.warnings)
    assert not any(f.check == "claims_represented" for f in report.failures)


def test_a_plan_with_no_atoms_fails() -> None:
    plan = {**GOOD_PLAN, "content_atoms": []}

    report = _check(plan)

    assert any(f.check == "claims_represented" for f in report.failures)


@pytest.mark.parametrize(
    "instruction",
    [
        "write like Thomas would write it",
        "match the author's voice throughout",
        "sentences should average 24 words",
        "use the same wording as the source",
        "the result must read as human-sounding",
        "keep the AI-detector score low",
    ],
)
def test_style_and_detector_instructions_are_rejected(instruction: str) -> None:
    plan = {**GOOD_PLAN, "content_atoms": [*GOOD_PLAN["content_atoms"], instruction]}

    report = _check(plan)

    assert any(f.check == "no_style_instructions" for f in report.failures), instruction


def test_a_style_instruction_hidden_in_immutable_details_is_still_rejected() -> None:
    plan = {
        **GOOD_PLAN,
        "immutable_details": [*GOOD_PLAN["immutable_details"], "imitate the writer's tone"],
    }

    report = _check(plan)

    assert any(f.check == "no_style_instructions" for f in report.failures)


# ---------------------------------------------------------------------------
# Leakage gates
# ---------------------------------------------------------------------------


def _record(example_id, source_id, split, text, region_ids=None, justification=None):
    return AnnotationRecord(
        example_id=example_id,
        source_id=source_id,
        split=split,
        region_ids=tuple(region_ids or (f"{source_id}:b0000",)),
        target_text=text,
        justification=justification,
    )


TRAIN_TEXT = _words(60, "train")
HOLDOUT_TEXT = _words(60, "held")


def test_a_disjoint_annotation_set_passes() -> None:
    records = [
        _record("a", "essay", "train", TRAIN_TEXT),
        _record("b", "diary", "holdout", HOLDOUT_TEXT),
    ]

    report = run_leakage_checks(records, holdout_source_ids=["diary"])

    assert report.passed
    assert report.checks_run


def test_a_holdout_source_in_train_is_fatal() -> None:
    records = [_record("a", "diary", "train", TRAIN_TEXT)]

    report = run_leakage_checks(records, holdout_source_ids=["diary"])

    assert any(f.check == "holdout_source_in_train" for f in report.fatal)


def test_an_other_author_target_is_fatal() -> None:
    records = [_record("a", "peer-response", "train", TRAIN_TEXT)]

    report = run_leakage_checks(
        records, holdout_source_ids=[], other_author_source_ids=["peer-response"]
    )

    assert any(f.check == "other_author_target" for f in report.fatal)


def test_targeting_an_excluded_region_is_fatal() -> None:
    records = [_record("a", "essay", "train", TRAIN_TEXT, region_ids=["essay:b0049"])]

    report = run_leakage_checks(
        records, holdout_source_ids=[], excluded_region_ids=["essay:b0049"]
    )

    assert any(f.check == "excluded_region_target" for f in report.fatal)


def test_an_exactly_duplicated_target_across_the_split_is_fatal() -> None:
    records = [
        _record("a", "essay", "train", TRAIN_TEXT),
        _record("b", "diary", "holdout", TRAIN_TEXT),
    ]

    report = run_leakage_checks(records, holdout_source_ids=["diary"])

    assert any(f.check == "exact_target_overlap" for f in report.fatal)


def test_a_strong_near_duplicate_across_the_split_is_fatal() -> None:
    shared = _words(50, "shared")
    records = [
        _record("a", "essay", "train", shared + " " + _words(5, "tail")),
        _record("b", "diary", "holdout", shared + " " + _words(5, "other")),
    ]

    report = run_leakage_checks(records, holdout_source_ids=["diary"])

    assert any(f.check == "near_duplicate_target_overlap" for f in report.fatal)
    assert report.max_train_holdout_ngram_overlap > 0.25


def test_reusing_a_region_across_two_train_examples_is_fatal_unless_justified() -> None:
    records = [
        _record("a", "essay", "train", TRAIN_TEXT, region_ids=["essay:b0000"]),
        _record("b", "essay", "train", _words(60, "other"), region_ids=["essay:b0000"]),
    ]

    report = run_leakage_checks(records, holdout_source_ids=[])

    assert any(f.check == "region_reused_across_examples" for f in report.fatal)


def test_a_justified_region_reuse_is_flagged_but_not_fatal() -> None:
    records = [
        _record("a", "essay", "train", TRAIN_TEXT, region_ids=["essay:b0000"]),
        _record(
            "b",
            "essay",
            "train",
            _words(60, "other"),
            region_ids=["essay:b0000"],
            justification="deliberate overlap approved during review",
        ),
    ]

    report = run_leakage_checks(records, holdout_source_ids=[])

    assert not report.passed
    assert report.fatal == ()
