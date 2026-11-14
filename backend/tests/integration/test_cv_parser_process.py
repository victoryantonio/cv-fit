"""The real out-of-process parser: the only path that is not faked.

It runs as a subprocess with a timeout, so these tests are slower than the rest
and are kept apart from the intake behaviour they support.
"""

from __future__ import annotations

import pytest

from app.modules.cvs.parser import DocumentParseError
from app.modules.cvs.parser_runner import SubprocessParser
from tests.fixtures.documents import build_docx


def test_subprocess_parser_reads_a_real_docx() -> None:
    """The only test that exercises the real out-of-process parser path."""
    parser = SubprocessParser(timeout_seconds=60)

    parsed = parser.parse(build_docx(), file_name="cv.docx")

    assert parsed.kind == "docx"
    assert "RINA PRATAMA" in parsed.text
    assert "experience" in parsed.sections


def test_subprocess_parser_reports_a_crash() -> None:
    parser = SubprocessParser(timeout_seconds=60)

    with pytest.raises(DocumentParseError, match="not a readable"):
        parser.parse(b"PK\x03\x04broken", file_name="cv.docx")


def test_subprocess_parser_survives_a_cv_that_is_not_ascii() -> None:
    """A bullet or a smart quote used to kill the worker and read as "no output".

    Windows pipes default to the ANSI codepage, so this failed before the protocol
    was pinned to UTF-8 end to end.
    """
    parser = SubprocessParser(timeout_seconds=60)
    text = "RINA PRATAMA\n● Built dashboards — plain words, “quoted”, naïve.\n"

    parsed = parser.parse(build_docx(text.splitlines()), file_name="cv.docx")

    assert "●" in parsed.text
    assert "—" in parsed.text
    assert "naïve" in parsed.text
