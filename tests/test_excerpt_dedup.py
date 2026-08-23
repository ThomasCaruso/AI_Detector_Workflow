from authorship_shift.corpus_pipeline import RawExcerpt
from authorship_shift.excerpt_dedup import audit_raw_excerpt_duplicates


def _excerpt(excerpt_id: str, source_id: str, text: str) -> RawExcerpt:
    return RawExcerpt(
        id=excerpt_id,
        source_id=source_id,
        genre="business_analysis",
        instruction="Explain the analysis.",
        target_text=text,
        excerpt_locator=f"locator-{excerpt_id}",
    )


def test_exact_duplicate_is_fatal_even_with_whitespace_reflow():
    left = _excerpt("a", "source-1", "The same human passage appears here.")
    right = _excerpt("b", "source-1", "The same  human\npassage appears here.")
    report = audit_raw_excerpt_duplicates([left, right])
    assert not report.valid
    assert len(report.exact_duplicates) == 1
    assert not report.cross_source_near_duplicates


def test_cross_source_near_duplicate_is_fatal():
    base = " ".join(f"token{i}" for i in range(60))
    changed = base.replace("token30", "different")
    report = audit_raw_excerpt_duplicates(
        [
            _excerpt("a", "source-1", base),
            _excerpt("b", "source-2", changed),
        ]
    )
    assert not report.valid
    assert not report.exact_duplicates
    assert len(report.cross_source_near_duplicates) == 1


def test_within_source_near_duplicate_warns_but_does_not_fail():
    base = " ".join(f"token{i}" for i in range(60))
    changed = base.replace("token30", "different")
    report = audit_raw_excerpt_duplicates(
        [
            _excerpt("a", "source-1", base),
            _excerpt("b", "source-1", changed),
        ]
    )
    assert report.valid
    assert len(report.within_source_near_duplicates) == 1


def test_unrelated_passages_are_clean():
    report = audit_raw_excerpt_duplicates(
        [
            _excerpt("a", "source-1", "alpha beta gamma delta epsilon zeta eta theta"),
            _excerpt("b", "source-2", "one two three four five six seven eight"),
        ]
    )
    assert report.valid
    assert not report.exact_duplicates
    assert not report.cross_source_near_duplicates
    assert not report.within_source_near_duplicates
