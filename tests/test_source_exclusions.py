import json

import pytest

from authorship_shift.corpus_pipeline import RawExcerpt
from authorship_shift.source_exclusions import (
    SourceExclusion,
    excerpt_source_pages,
    load_registry_source_exclusions,
    validate_excerpt_pages,
)
from authorship_shift.text_derivation import PageText


def _excerpt(*, text="Allowed prose here.", pages=None):
    return RawExcerpt(
        id="ex-1",
        source_id="source-1",
        genre="business_analysis",
        instruction="Explain the analysis.",
        target_text=text,
        excerpt_locator="p. 2",
        metadata={"source_pages": [2] if pages is None else pages},
    )


def test_registry_source_exclusion_parses_and_normalizes_pages(tmp_path):
    path = tmp_path / "registry.json"
    path.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "source-1",
                        "source_exclusions": [
                            {
                                "pages": [3, 1, 3],
                                "category": "rights",
                                "reason": "Third-party cover image.",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    exclusions, errors = load_registry_source_exclusions(path)
    assert errors == []
    assert exclusions["source-1"][0].pages == (1, 3)


def test_excluded_page_is_rejected():
    excerpt = _excerpt(pages=[1])
    pages = [PageText(1, "Third-party cover material."), PageText(2, "Allowed prose here.")]
    exclusions = (
        SourceExclusion((1,), "rights", "Third-party cover image and credit."),
    )
    with pytest.raises(ValueError, match="excluded for rights"):
        validate_excerpt_pages(excerpt, pages, exclusions)


def test_declared_source_page_must_contain_target():
    excerpt = _excerpt(text="Allowed prose here.", pages=[1])
    pages = [PageText(1, "Other text."), PageText(2, "Allowed prose here.")]
    with pytest.raises(ValueError, match="declared source_pages"):
        validate_excerpt_pages(excerpt, pages, tuple())


def test_valid_pdf_excerpt_accepts_whitespace_reflow_on_declared_page():
    excerpt = _excerpt(text="Allowed prose here.", pages=[2])
    pages = [PageText(1, "Other text."), PageText(2, "Allowed\nprose   here.")]
    assert validate_excerpt_pages(excerpt, pages, tuple()) == (2,)


def test_pdf_excerpt_requires_source_pages():
    excerpt = _excerpt(pages=[])
    with pytest.raises(ValueError, match="source_pages"):
        excerpt_source_pages(excerpt)
