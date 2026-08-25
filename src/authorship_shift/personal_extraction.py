"""Deterministic extraction for the user-owned personal-style corpus.

The personal corpus uses the lightweight contract documented in
``research/lora/PERSONAL_STYLE_CORPUS.md``:

    artifact SHA-256
    -> deterministic format-specific extraction
    -> extracted-text SHA-256
    -> frozen eligible region IDs
    -> semantic plan
    -> immutable target prose

This module packages the extraction behaviour that produced the frozen
Experiment B audit so it can be re-run and hash-compared. It deliberately does
not normalise spelling, punctuation, capitalisation, grammar, whitespace, or
paragraph boundaries: those imperfections are part of the writing distribution
being modelled.

DOCX is read straight from OOXML rather than converted through PDF. PDF uses a
pinned ``pypdf`` build and is only trusted when its text layer is already clean;
:func:`assess_pdf_text_layer` decides that, and a failing PDF must be escalated
to the general canonical-correction workflow instead of silently repaired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import re
from typing import Iterable, Sequence
import xml.etree.ElementTree as ET
import zipfile

DOCX_EXTRACTOR_NAME = "personal-docx"
DOCX_EXTRACTOR_VERSION = "v1"
PDF_EXTRACTOR_NAME = "personal-pdf"
PDF_EXTRACTOR_VERSION = "v1"
PDF_PINNED_PYPDF_VERSION = "6.15.0"

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Body first, then comments, then header/footer chrome. Block order within a
# part is document order, so region ordinals are stable across re-extraction.
_PART_ORDER = ("body", "comment", "header_footer")

# Separator used to build the extracted-text digest. Chosen once and pinned:
# changing it changes every extracted_text_sha256 and therefore breaks the
# frozen contract.
_TEXT_DIGEST_SEPARATOR = "\n"


@dataclass(frozen=True)
class Region:
    """One extracted, ordinally-identified block of source text."""

    region_id: str
    block_index: int
    part: str
    style: str | None
    in_table: bool
    text: str
    page: int | None = None

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass(frozen=True)
class PersonalExtraction:
    """Deterministic extraction result for one personal source artifact."""

    source_id: str
    original_filename: str
    artifact_kind: str
    artifact_sha256: str
    extractor_name: str
    extractor_version: str
    extracted_text_sha256: str
    parts_present: tuple[str, ...]
    regions: tuple[Region, ...]
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def block_count(self) -> int:
        return len(self.regions)

    @property
    def word_count(self) -> int:
        return sum(region.word_count for region in self.regions)

    def region(self, region_id: str) -> Region:
        for candidate in self.regions:
            if candidate.region_id == region_id:
                return candidate
        raise KeyError(f"unknown region_id {region_id!r} in {self.source_id}")

    def provenance(self) -> dict[str, str]:
        """The four fields every included source must record."""

        return {
            "artifact_sha256": self.artifact_sha256,
            "extractor_name": self.extractor_name,
            "extractor_version": self.extractor_version,
            "extracted_text_sha256": self.extracted_text_sha256,
        }


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def region_id_for(source_id: str, block_index: int) -> str:
    """Stable region identifier.

    The ordinal is the document-order block index, which is what the frozen
    Experiment B region-exclusion mask already refers to. Keeping the ordinal
    means a frozen exclusion never silently points at different prose.
    """

    return f"{source_id}:b{block_index:04d}"


def extracted_text_digest(texts: Iterable[str]) -> str:
    """Digest of ordered region text.

    Deterministic given identical region text and ordering, so re-running
    extraction on an unchanged artifact reproduces the same value.
    """

    joined = _TEXT_DIGEST_SEPARATOR.join(texts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


# Tabs and in-paragraph breaks are whitespace inside a single paragraph. They
# each render as one space so that words either side stay separate words, and so
# that a leading first-line tab survives as leading whitespace.
_WHITESPACE_TAGS = frozenset({f"{_W_NS}tab", f"{_W_NS}br", f"{_W_NS}cr"})
_TEXT_TAG = f"{_W_NS}t"


def _paragraph_text(paragraph: ET.Element) -> str:
    pieces: list[str] = []
    for node in paragraph.iter():
        if node.tag == _TEXT_TAG:
            pieces.append(node.text or "")
        elif node.tag in _WHITESPACE_TAGS:
            pieces.append(" ")
    return "".join(pieces)


def _paragraph_style(paragraph: ET.Element) -> str | None:
    properties = paragraph.find(f"{_W_NS}pPr")
    if properties is None:
        return None
    style = properties.find(f"{_W_NS}pStyle")
    if style is None:
        return None
    return style.get(f"{_W_NS}val")


def _iter_paragraphs(root: ET.Element) -> Iterable[tuple[ET.Element, bool]]:
    """Yield ``(paragraph, in_table)`` in document order.

    Table cell paragraphs are reported in place rather than hoisted, so the
    ordinal sequence follows how the document actually reads.
    """

    table_paragraphs = {
        id(paragraph)
        for table in root.iter(f"{_W_NS}tbl")
        for paragraph in table.iter(f"{_W_NS}p")
    }
    for paragraph in root.iter(f"{_W_NS}p"):
        yield paragraph, id(paragraph) in table_paragraphs


def _docx_parts_present(archive: zipfile.ZipFile) -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name in archive.namelist()
            if name.startswith("word/")
            and name.endswith(".xml")
            and "/_rels/" not in name
        )
    )


def _docx_part_names(archive: zipfile.ZipFile) -> dict[str, list[str]]:
    names = set(archive.namelist())
    header_footer = sorted(
        name
        for name in names
        if re.fullmatch(r"word/(header|footer)\d+\.xml", name)
    )
    return {
        "body": ["word/document.xml"] if "word/document.xml" in names else [],
        "comment": ["word/comments.xml"] if "word/comments.xml" in names else [],
        "header_footer": header_footer,
    }


def extract_docx(
    path: str,
    *,
    source_id: str,
    original_filename: str | None = None,
) -> PersonalExtraction:
    """Extract a DOCX directly from OOXML, preserving document order.

    Empty paragraphs carry no prose and are dropped, so they never consume an
    ordinal. Everything that survives keeps its original characters verbatim.
    """

    artifact_sha256 = sha256_file(path)
    regions: list[Region] = []

    with zipfile.ZipFile(path) as archive:
        parts_present = _docx_parts_present(archive)
        part_names = _docx_part_names(archive)
        for part in _PART_ORDER:
            for name in part_names[part]:
                root = ET.fromstring(archive.read(name))
                for paragraph, in_table in _iter_paragraphs(root):
                    text = _paragraph_text(paragraph)
                    if not text.strip():
                        continue
                    block_index = len(regions)
                    regions.append(
                        Region(
                            region_id=region_id_for(source_id, block_index),
                            block_index=block_index,
                            part=part,
                            style=_paragraph_style(paragraph),
                            in_table=in_table,
                            text=text,
                        )
                    )

    return PersonalExtraction(
        source_id=source_id,
        original_filename=original_filename or path.replace("\\", "/").rsplit("/", 1)[-1],
        artifact_kind="docx",
        artifact_sha256=artifact_sha256,
        extractor_name=DOCX_EXTRACTOR_NAME,
        extractor_version=DOCX_EXTRACTOR_VERSION,
        extracted_text_sha256=extracted_text_digest(region.text for region in regions),
        parts_present=parts_present,
        regions=tuple(regions),
    )


PDF_LAYOUT_EXTRACTOR_NAME = "personal-pdf-layout"
PDF_LAYOUT_EXTRACTOR_VERSION = "v1"

# A first line indented past this many columns starts a new block. Continuation
# lines in a justified body sit at column 0; a paragraph's first line carries the
# document's first-line indent, and a centred title carries far more.
_PDF_INDENT_THRESHOLD = 4


def reconstruct_pdf_paragraphs(
    page_texts: Sequence[str],
    *,
    indent_threshold: int = _PDF_INDENT_THRESHOLD,
) -> tuple[tuple[str, ...], tuple[int, ...]]:
    """Rebuild paragraphs from layout-mode PDF text.

    ``extract_text(extraction_mode="layout")`` preserves horizontal position as
    leading spaces, which is what makes paragraph boundaries recoverable from a
    renderer whose default text layer emits one word per line. Lines are joined
    with a single space; a line whose indent clears ``indent_threshold`` opens a
    new block.

    Returns ``(blocks, indents)`` where ``indents`` is each block's first-line
    indent, so a caller can tell a centred title from body text without
    re-deriving it.

    This reads position, not meaning. It does not repair hyphenation, respace
    words, or alter characters; callers should still check for line-break
    hyphenation before trusting the result as target prose.
    """

    lines: list[tuple[int, str]] = []
    for text in page_texts:
        for raw in text.splitlines():
            if raw.strip():
                lines.append((len(raw) - len(raw.lstrip()), raw.strip()))

    blocks: list[str] = []
    indents: list[int] = []
    current: list[str] = []
    current_indent = 0
    for indent, text in lines:
        if indent >= indent_threshold:
            if current:
                blocks.append(" ".join(current))
                indents.append(current_indent)
            current = [text]
            current_indent = indent
        elif current:
            current.append(text)
        else:
            current = [text]
            current_indent = indent
    if current:
        blocks.append(" ".join(current))
        indents.append(current_indent)

    return tuple(blocks), tuple(indents)


def find_linebreak_hyphenation(page_texts: Sequence[str]) -> tuple[str, ...]:
    """Lines ending in a hyphen, which joining would silently fuse into one word.

    Returned for review rather than repaired: deciding whether "self- evident"
    was hyphenated by the author or broken by the renderer is a judgement about
    the source, not something an extractor should guess.
    """

    return tuple(
        line.strip()
        for text in page_texts
        for line in text.splitlines()
        if line.strip().endswith("-")
    )


@dataclass(frozen=True)
class PdfTextLayerAssessment:
    """Whether a PDF's existing text layer can carry target prose as-is."""

    clean: bool
    reasons: tuple[str, ...]
    line_count: int
    single_word_line_ratio: float
    doubled_space_lines: int

    @property
    def requires_escalation(self) -> bool:
        return not self.clean


def assess_pdf_text_layer(
    page_texts: Sequence[str],
    *,
    single_word_line_limit: float = 0.5,
) -> PdfTextLayerAssessment:
    """Decide whether a PDF text layer is clean enough for the light contract.

    Two artifacts disqualify a text layer because both change eligible target
    prose rather than merely its presentation:

    * shredded lines - renderers that emit one word per line destroy the
      paragraph boundaries the contract requires be preserved;
    * doubled intra-line spacing - word spacing has been rewritten, so target
      text would no longer match the user's prose character-for-character.

    A failing assessment means escalate that one source to the canonical
    correction workflow. It never licenses repairing the text in place here.
    """

    lines = [line for text in page_texts for line in text.splitlines() if line.strip()]
    if not lines:
        return PdfTextLayerAssessment(
            clean=False,
            reasons=("no extractable text lines",),
            line_count=0,
            single_word_line_ratio=0.0,
            doubled_space_lines=0,
        )

    single_word_lines = sum(1 for line in lines if len(line.split()) == 1)
    ratio = single_word_lines / len(lines)
    doubled = sum(1 for line in lines if "  " in line.strip())

    reasons: list[str] = []
    if ratio > single_word_line_limit:
        reasons.append(
            f"{single_word_lines}/{len(lines)} extracted lines hold a single word; "
            "paragraph boundaries are not recoverable from the text layer"
        )
    if doubled:
        reasons.append(
            f"{doubled} extracted line(s) contain doubled intra-line spacing; "
            "word spacing does not match the source prose"
        )

    return PdfTextLayerAssessment(
        clean=not reasons,
        reasons=tuple(reasons),
        line_count=len(lines),
        single_word_line_ratio=ratio,
        doubled_space_lines=doubled,
    )
