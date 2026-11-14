"""Upload validation: the extension must agree with the bytes, and size is capped."""

from __future__ import annotations

import io
import zipfile

import pytest

from app.modules.cvs.service import detect_kind
from app.shared.errors import AppError
from tests.fixtures.documents import build_docx, build_pdf


def _zip_without_document_xml() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/styles.xml", "<styles/>")
    return buffer.getvalue()


def test_valid_pdf_passes() -> None:
    assert detect_kind("cv.pdf", build_pdf()) == "pdf"


def test_valid_docx_passes() -> None:
    assert detect_kind("cv.docx", build_docx()) == "docx"


def test_extension_is_case_insensitive() -> None:
    assert detect_kind("CV.PDF", build_pdf()) == "pdf"


@pytest.mark.parametrize("file_name", ["cv.txt", "cv.rtf", "cv", "cv.doc", "cv.exe", "cv.pdf.exe"])
def test_unsupported_extension_is_rejected(file_name: str) -> None:
    with pytest.raises(AppError) as caught:
        detect_kind(file_name, build_pdf())

    assert caught.value.code == "UPLOAD_INVALID"
    assert caught.value.details["reason"] == "extension"


def test_pdf_extension_with_docx_bytes_is_rejected() -> None:
    with pytest.raises(AppError) as caught:
        detect_kind("cv.pdf", build_docx())

    assert caught.value.code == "UPLOAD_INVALID"
    assert caught.value.details["reason"] == "magic_bytes"


def test_docx_extension_with_pdf_bytes_is_rejected() -> None:
    with pytest.raises(AppError) as caught:
        detect_kind("cv.docx", build_pdf())

    assert caught.value.code == "UPLOAD_INVALID"
    assert caught.value.details["reason"] == "magic_bytes"


def test_zip_that_is_not_a_docx_is_rejected() -> None:
    with pytest.raises(AppError) as caught:
        detect_kind("cv.docx", _zip_without_document_xml())

    assert caught.value.details["reason"] == "magic_bytes"


@pytest.mark.parametrize(
    "payload",
    [b"\x00" * 64, b"PK\x03\x04 truncated", b"#!/bin/sh\nrm -rf /\n", b"<?xml version='1.0'?>"],
)
def test_noise_is_rejected(payload: bytes) -> None:
    with pytest.raises(AppError):
        detect_kind("cv.pdf", payload)


def test_magic_bytes_alone_do_not_prove_a_readable_file() -> None:
    """Validation only checks the container; the parser decides readability."""
    assert detect_kind("cv.pdf", b"%PDF-") == "pdf"
