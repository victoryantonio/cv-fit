"""Parser output is the weakest link, so warnings are tested, not assumed."""

from __future__ import annotations

import pytest

from app.modules.cvs.parser import (
    DocumentParseError,
    parse_document,
    parse_docx,
    parse_pdf,
    split_sections,
)
from tests.fixtures.documents import (
    CV_LINES,
    build_docx,
    build_docx_with_table,
    build_pdf,
    build_textless_pdf,
    build_two_column_pdf,
)


def test_docx_yields_text_and_sections() -> None:
    parsed = parse_docx(build_docx())

    assert parsed.kind == "docx"
    assert parsed.warnings == []
    assert set(parsed.sections) == {
        "other",
        "summary",
        "experience",
        "education",
        "skills",
        "projects",
    }
    assert "Rebuilt the settlement worker" in parsed.sections["experience"]


def test_docx_tables_are_extracted() -> None:
    parsed = parse_docx(build_docx_with_table())

    assert "Python | 6 years" in parsed.text


def test_short_document_raises_a_warning_not_an_error() -> None:
    parsed = parse_docx(build_docx(["Summary", "Python developer."]))

    assert "text_short" in parsed.warnings


def test_pdf_yields_text() -> None:
    parsed = parse_pdf(build_pdf())

    assert parsed.kind == "pdf"
    assert parsed.page_count == 1
    assert "RINA PRATAMA" in parsed.text
    assert parsed.warnings == []


def test_pdf_without_text_layer_is_flagged() -> None:
    parsed = parse_pdf(build_textless_pdf())

    assert "no_text_layer" in parsed.warnings
    assert parsed.text == ""


def test_two_column_pdf_is_flagged_as_garble() -> None:
    parsed = parse_pdf(build_two_column_pdf())

    assert "multi_column_suspected" in parsed.warnings


def test_single_column_pdf_is_not_flagged() -> None:
    parsed = parse_pdf(build_pdf(CV_LINES * 3))

    assert "multi_column_suspected" not in parsed.warnings


def test_unreadable_pdf_raises() -> None:
    with pytest.raises(DocumentParseError):
        parse_pdf(b"not a pdf at all")


def test_split_sections_keeps_preamble_in_other() -> None:
    sections = split_sections("RINA PRATAMA\nSkills\nPython\nExperience\nEngineer")

    assert sections["other"] == "RINA PRATAMA"
    assert sections["skills"] == "Skills\nPython"
    assert sections["experience"] == "Experience\nEngineer"


@pytest.mark.parametrize("file_name", ["cv.txt", "cv.pdf.exe", "cv"])
def test_unsupported_extension_raises(file_name: str) -> None:
    with pytest.raises(DocumentParseError):
        parse_document(b"whatever", file_name=file_name)


def test_parse_document_dispatches_on_extension() -> None:
    assert parse_document(build_docx(), file_name="cv.DOCX").kind == "docx"
    assert parse_document(build_pdf(), file_name="cv.pdf").kind == "pdf"
