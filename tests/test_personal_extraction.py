"""Tests for the personal-style corpus extraction contract.

These build synthetic DOCX archives in a tmp_path so the suite never depends on
the gitignored personal corpus or on any of the user's real prose.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import zipfile

import pytest

from authorship_shift.personal_extraction import (
    DOCX_EXTRACTOR_NAME,
    DOCX_EXTRACTOR_VERSION,
    assess_pdf_text_layer,
    extract_docx,
    extracted_text_digest,
    region_id_for,
    sha256_file,
)

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def _paragraph(text: str, *, style: str | None = None, leading_tab: bool = False) -> str:
    properties = f"<w:pPr><w:pStyle w:val=\"{style}\"/></w:pPr>" if style else ""
    tab = "<w:r><w:tab/></w:r>" if leading_tab else ""
    return (
        f"<w:p>{properties}{tab}"
        f'<w:r><w:t xml:space="preserve">{text}</w:t></w:r></w:p>'
    )


def _document(body: str) -> bytes:
    return f'<w:document {W}><w:body>{body}</w:body></w:document>'.encode("utf-8")


def _write_docx(path: Path, body: str, *, extra_parts: dict[str, bytes] | None = None) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("_rels/.rels", "<Relationships/>")
        archive.writestr("word/_rels/document.xml.rels", "<Relationships/>")
        archive.writestr("word/document.xml", _document(body))
        archive.writestr("word/styles.xml", f"<w:styles {W}/>")
        for name, payload in (extra_parts or {}).items():
            archive.writestr(name, payload)
    return path


def test_extraction_records_the_four_required_provenance_fields(tmp_path: Path) -> None:
    path = _write_docx(tmp_path / "sample.docx", _paragraph("First idea."))

    extraction = extract_docx(str(path), source_id="sample")

    assert extraction.provenance() == {
        "artifact_sha256": sha256_file(str(path)),
        "extractor_name": DOCX_EXTRACTOR_NAME,
        "extractor_version": DOCX_EXTRACTOR_VERSION,
        "extracted_text_sha256": hashlib.sha256(b"First idea.").hexdigest(),
    }


def test_re_extraction_reproduces_the_extracted_text_hash(tmp_path: Path) -> None:
    path = _write_docx(
        tmp_path / "sample.docx",
        _paragraph("One.") + _paragraph("Two.") + _paragraph("Three."),
    )

    first = extract_docx(str(path), source_id="sample")
    second = extract_docx(str(path), source_id="sample")

    assert first.extracted_text_sha256 == second.extracted_text_sha256
    assert [region.region_id for region in first.regions] == [
        region.region_id for region in second.regions
    ]


def test_region_ids_are_ordinal_and_document_ordered(tmp_path: Path) -> None:
    path = _write_docx(
        tmp_path / "sample.docx",
        _paragraph("Alpha.") + _paragraph("Beta.") + _paragraph("Gamma."),
    )

    extraction = extract_docx(str(path), source_id="essay")

    assert [region.region_id for region in extraction.regions] == [
        "essay:b0000",
        "essay:b0001",
        "essay:b0002",
    ]
    assert [region.text for region in extraction.regions] == ["Alpha.", "Beta.", "Gamma."]
    assert extraction.region("essay:b0001").text == "Beta."


def test_region_id_ordinal_matches_frozen_block_index() -> None:
    # The frozen Experiment B exclusion mask refers to integer block indices, so
    # a region id must stay derivable from one.
    assert region_id_for("final-portfolio", 49) == "final-portfolio:b0049"


def test_empty_paragraphs_do_not_consume_an_ordinal(tmp_path: Path) -> None:
    path = _write_docx(
        tmp_path / "sample.docx",
        _paragraph("Kept.") + "<w:p/>" + _paragraph("   ") + _paragraph("Also kept."),
    )

    extraction = extract_docx(str(path), source_id="sample")

    assert [(r.block_index, r.text) for r in extraction.regions] == [
        (0, "Kept."),
        (1, "Also kept."),
    ]


def test_prose_is_preserved_without_normalisation(tmp_path: Path) -> None:
    # Curly quotes, a doubled space, a non-breaking space and a lowercase
    # sentence start all survive verbatim: they are part of the distribution.
    raw = "“mere presence”  is odd,and i kept it"
    path = _write_docx(tmp_path / "sample.docx", _paragraph(raw))

    extraction = extract_docx(str(path), source_id="sample")

    assert extraction.regions[0].text == raw


def test_tabs_and_breaks_render_as_single_spaces(tmp_path: Path) -> None:
    body = (
        _paragraph("Indented idea.", leading_tab=True)
        + '<w:p><w:r><w:t xml:space="preserve">Label:</w:t>'
        '<w:br/><w:br/><w:t xml:space="preserve">Body.</w:t></w:r></w:p>'
    )
    path = _write_docx(tmp_path / "sample.docx", body)

    extraction = extract_docx(str(path), source_id="sample")

    assert extraction.regions[0].text == " Indented idea."
    # Two breaks keep "Label:" and "Body." as separate words rather than fusing.
    assert extraction.regions[1].text == "Label:  Body."
    assert extraction.regions[1].word_count == 2


def test_table_paragraphs_are_flagged_in_document_order(tmp_path: Path) -> None:
    body = (
        _paragraph("Before table.")
        + f"<w:tbl><w:tr><w:tc>{_paragraph('Cell value')}</w:tc></w:tr></w:tbl>"
        + _paragraph("After table.")
    )
    path = _write_docx(tmp_path / "sample.docx", body)

    extraction = extract_docx(str(path), source_id="sample")

    assert [(r.text, r.in_table) for r in extraction.regions] == [
        ("Before table.", False),
        ("Cell value", True),
        ("After table.", False),
    ]


def test_paragraph_style_is_recorded(tmp_path: Path) -> None:
    body = _paragraph("A heading", style="Heading2") + _paragraph("Plain body.")
    path = _write_docx(tmp_path / "sample.docx", body)

    extraction = extract_docx(str(path), source_id="sample")

    assert [r.style for r in extraction.regions] == ["Heading2", None]


def test_body_precedes_comments_which_precede_header_footer(tmp_path: Path) -> None:
    path = _write_docx(
        tmp_path / "sample.docx",
        _paragraph("Body prose."),
        extra_parts={
            "word/comments.xml": f'<w:comments {W}>{_paragraph("Reviewer note.")}</w:comments>',
            "word/header1.xml": f'<w:hdr {W}>{_paragraph("Whitlock 1")}</w:hdr>',
        },
    )

    extraction = extract_docx(str(path), source_id="sample")

    assert [(r.part, r.text) for r in extraction.regions] == [
        ("body", "Body prose."),
        ("comment", "Reviewer note."),
        ("header_footer", "Whitlock 1"),
    ]


def test_parts_present_lists_sorted_word_xml_parts(tmp_path: Path) -> None:
    path = _write_docx(
        tmp_path / "sample.docx",
        _paragraph("Body."),
        extra_parts={"word/header1.xml": f'<w:hdr {W}/>'},
    )

    extraction = extract_docx(str(path), source_id="sample")

    # Relationship parts and [Content_Types].xml are packaging, not content.
    assert extraction.parts_present == (
        "word/document.xml",
        "word/header1.xml",
        "word/styles.xml",
    )


def test_extracted_text_digest_depends_on_region_order() -> None:
    assert extracted_text_digest(["a", "b"]) != extracted_text_digest(["b", "a"])


def test_unknown_region_id_raises(tmp_path: Path) -> None:
    path = _write_docx(tmp_path / "sample.docx", _paragraph("Only block."))
    extraction = extract_docx(str(path), source_id="sample")

    with pytest.raises(KeyError):
        extraction.region("sample:b0099")


def test_clean_pdf_text_layer_needs_no_escalation() -> None:
    assessment = assess_pdf_text_layer(
        [
            "The community I am researching is small.\n"
            "It shares a set of common obstacles.\n",
            "A second page of ordinary prose lines.\n",
        ]
    )

    assert assessment.clean
    assert not assessment.requires_escalation
    assert assessment.reasons == ()


def test_one_word_per_line_pdf_requires_escalation() -> None:
    # Some renderers emit each word as its own line, which destroys the
    # paragraph boundaries the contract requires be preserved.
    shredded = "\n \n".join("the community I am choosing to research is small".split())

    assessment = assess_pdf_text_layer([shredded])

    assert assessment.requires_escalation
    assert assessment.single_word_line_ratio > 0.5
    assert any("single word" in reason for reason in assessment.reasons)


def test_doubled_intra_line_spacing_requires_escalation() -> None:
    assessment = assess_pdf_text_layer(["Widget  Catalogue   The  sample  is  small.\n"])

    assert assessment.requires_escalation
    assert assessment.doubled_space_lines == 1
    assert any("doubled intra-line spacing" in reason for reason in assessment.reasons)


def test_empty_pdf_text_layer_requires_escalation() -> None:
    assessment = assess_pdf_text_layer(["", "   \n"])

    assert assessment.requires_escalation
    assert assessment.line_count == 0


# ---------------------------------------------------------------------------
# Layout-mode PDF paragraph reconstruction
# ---------------------------------------------------------------------------

from authorship_shift.personal_extraction import (  # noqa: E402
    PDF_LAYOUT_EXTRACTOR_NAME,
    PDF_LAYOUT_EXTRACTOR_VERSION,
    find_linebreak_hyphenation,
    reconstruct_pdf_paragraphs,
)


def test_indented_first_lines_open_new_blocks() -> None:
    page = (
        "        The first paragraph starts here\n"
        "and continues on this line\n"
        "and this one.\n"
        "        The second paragraph starts here\n"
        "and continues.\n"
    )

    blocks, indents = reconstruct_pdf_paragraphs([page])

    assert len(blocks) == 2
    assert blocks[0] == "The first paragraph starts here and continues on this line and this one."
    assert blocks[1] == "The second paragraph starts here and continues."
    assert indents == (8, 8)


def test_a_centred_title_is_separable_by_its_indent() -> None:
    page = (
        "                    A Centred Title\n"
        "        Body text begins here\n"
        "and runs on.\n"
    )

    blocks, indents = reconstruct_pdf_paragraphs([page])

    assert blocks[0] == "A Centred Title"
    assert indents[0] > indents[1]


def test_blocks_span_page_boundaries() -> None:
    first = "        A paragraph that begins on one page\nand keeps going\n"
    second = "to the next page without a new indent.\n"

    blocks, _ = reconstruct_pdf_paragraphs([first, second])

    assert len(blocks) == 1
    assert blocks[0].endswith("without a new indent.")


def test_blank_lines_do_not_create_blocks() -> None:
    page = "        Only paragraph here\n\n   \nand its continuation.\n"

    blocks, _ = reconstruct_pdf_paragraphs([page])

    assert len(blocks) == 1


def test_reconstruction_is_deterministic() -> None:
    page = "        Alpha beta\ngamma delta\n        Epsilon zeta\n"

    assert reconstruct_pdf_paragraphs([page]) == reconstruct_pdf_paragraphs([page])


def test_reconstruction_preserves_characters_verbatim() -> None:
    page = "        “Curly quotes” and an em-dash — kept,and odd spacing\nsurvives.\n"

    blocks, _ = reconstruct_pdf_paragraphs([page])

    assert "“Curly quotes”" in blocks[0]
    assert "—" in blocks[0]
    assert "kept,and" in blocks[0]


def test_an_unindented_document_yields_one_block() -> None:
    page = "no indent anywhere\njust running text\nacross lines\n"

    blocks, indents = reconstruct_pdf_paragraphs([page])

    assert len(blocks) == 1
    assert indents == (0,)


def test_indent_threshold_is_configurable() -> None:
    page = "  Two space indent\nand a continuation.\n"

    default_blocks, _ = reconstruct_pdf_paragraphs([page])
    strict_blocks, _ = reconstruct_pdf_paragraphs([page], indent_threshold=2)

    assert len(default_blocks) == 1
    assert len(strict_blocks) == 1  # single leading block either way
    assert strict_blocks[0].startswith("Two space indent")


def test_linebreak_hyphenation_is_reported_not_repaired() -> None:
    page = "        A word broken self-\nevident across a line break.\n"

    found = find_linebreak_hyphenation([page])
    blocks, _ = reconstruct_pdf_paragraphs([page])

    assert found == ("A word broken self-",)
    # Reported, and the joined text still shows the break for a human to judge.
    assert "self- evident" in blocks[0]


def test_clean_pages_report_no_hyphenation() -> None:
    assert find_linebreak_hyphenation(["        No breaks here\nat all.\n"]) == ()


def test_layout_extractor_is_pinned() -> None:
    assert PDF_LAYOUT_EXTRACTOR_NAME == "personal-pdf-layout"
    assert PDF_LAYOUT_EXTRACTOR_VERSION == "v1"
