from authorship_shift.hyphenation_review import suggest_linebreak_hyphenation
from authorship_shift.text_derivation import PageText


def _by_old(items):
    return {item.old: item for item in items}


def test_same_document_evidence_classifies_join_keep_conflict_and_unresolved():
    pages = [
        PageText(
            1,
            "The charac-\nteristics matter. Elsewhere characteristics recur. "
            "A full-\nload condition appears, and full-load is used inline.",
        ),
        PageText(
            2,
            "One govern-\nment case appears. Both government and govern-ment are present. "
            "A phe-\nnomenon appears without another spelling.",
        ),
    ]

    items = _by_old(suggest_linebreak_hyphenation(pages))
    assert items["charac-\nteristics"].verdict == "JOIN"
    assert items["charac-\nteristics"].proposed_new == "characteristics"
    assert items["full-\nload"].verdict == "KEEP"
    assert items["full-\nload"].proposed_new == "full-load"
    assert items["govern-\nment"].verdict == "CONFLICT"
    assert items["govern-\nment"].proposed_new is None
    assert items["phe-\nnomenon"].verdict == "UNRESOLVED"
    assert items["phe-\nnomenon"].proposed_new is None


def test_evidence_search_is_case_insensitive_and_word_bounded():
    pages = [
        PageText(1, "Economy-\nwide effects matter."),
        PageText(2, "ECONOMYWIDE analysis appears elsewhere. Uneconomywideish does not count."),
    ]
    item = suggest_linebreak_hyphenation(pages)[0]
    assert item.verdict == "JOIN"
    assert item.joined_evidence_count == 1


def test_repeated_same_page_break_reports_exact_expected_count():
    pages = [
        PageText(1, "guar-\nantees and guar-\nantees"),
        PageText(2, "guarantees appear elsewhere"),
    ]
    items = suggest_linebreak_hyphenation(pages)
    assert len(items) == 1
    assert items[0].expected_count == 2
    assert items[0].verdict == "JOIN"


def test_alphanumeric_designators_are_detected_and_protected_by_inline_evidence():
    pages = [
        PageText(1, "COVID-\n19 affected the program. DDG-\n51 and F/A-\n18 were discussed."),
        PageText(2, "COVID-19 recurs. DDG-51 recurs. F/A-18 recurs."),
    ]
    items = _by_old(suggest_linebreak_hyphenation(pages))

    assert items["COVID-\n19"].verdict == "KEEP"
    assert items["COVID-\n19"].proposed_new == "COVID-19"
    assert items["DDG-\n51"].verdict == "KEEP"
    assert items["DDG-\n51"].proposed_new == "DDG-51"
    assert items["F/A-\n18"].verdict == "KEEP"
    assert items["F/A-\n18"].proposed_new == "F/A-18"


def test_numeric_footnote_interruption_is_detected_but_not_guessed():
    pages = [PageText(1, "The businesses accept-\n32. Additional prose follows.")]
    item = suggest_linebreak_hyphenation(pages)[0]
    assert item.old == "accept-\n32"
    assert item.verdict == "UNRESOLVED"
    assert item.proposed_new is None


def test_review_is_advisory_and_does_not_mutate_page_text():
    page = PageText(1, "full-\nload and full-load")
    before = page.text
    suggest_linebreak_hyphenation([page])
    assert page.text == before
