"""Synthetic CV documents, generated at test time so no binaries live in the repo."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Sequence

import docx
import pymupdf

CV_LINES: tuple[str, ...] = (
    "RINA PRATAMA",
    "rina.pratama@example.com | +62 812-3456-7890",
    "Jl. Melati No. 12, Bandung 40123",
    "SUMMARY",
    "Backend engineer with six years building payment and ledger services in Python.",
    "Comfortable owning a service from schema design through on-call.",
    "EXPERIENCE",
    "Senior Backend Engineer, PT Contoh Jaya, 2021 - 2024",
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes.",
    "Introduced contract tests across three services, cutting integration incidents per release.",
    "EDUCATION",
    "BSc Computer Science, Institut Teknologi Bandung, 2014 - 2018",
    "SKILLS",
    "Python, SQL, PostgreSQL, Redis, Docker, pytest, FastAPI, Kafka",
    "PROJECTS",
    "Ledger replay tool: re-processes a day of events from an immutable log.",
)


def build_docx(lines: Sequence[str] = CV_LINES) -> bytes:
    document = docx.Document()
    for line in lines:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return _stabilise_zip(buffer.getvalue())


def build_docx_with_table(lines: Sequence[str] = CV_LINES) -> bytes:
    document = docx.Document()
    document.add_paragraph(lines[0])
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Python"
    table.cell(0, 1).text = "6 years"
    table.cell(1, 0).text = "PostgreSQL"
    table.cell(1, 1).text = "5 years"
    for line in lines[1:]:
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return _stabilise_zip(buffer.getvalue())


def _stabilise_zip(archive: bytes) -> bytes:
    """Rewrite zip entry timestamps so the same document always hashes the same.

    python-docx writes each entry with the current clock time, which made two
    uploads of an "identical" file differ by hash whenever a second boundary fell
    between them.
    """
    source = zipfile.ZipFile(io.BytesIO(archive))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
        for item in source.infolist():
            entry = zipfile.ZipInfo(item.filename, date_time=(2024, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = item.external_attr
            target.writestr(entry, source.read(item.filename))
    source.close()
    return buffer.getvalue()


def build_pdf(lines: Sequence[str] = CV_LINES) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    y = 72.0
    for line in lines:
        page.insert_text((72, y), line, fontsize=10)
        y += 14.0
    data = document.tobytes()
    document.close()
    return data


def build_textless_pdf() -> bytes:
    """A scan-like page: drawings only, no text layer."""
    document = pymupdf.open()
    page = document.new_page()
    page.draw_rect(pymupdf.Rect(72, 72, 500, 700), color=(0.2, 0.2, 0.2), width=1)
    data = document.tobytes()
    document.close()
    return data


def build_two_column_pdf(rows: int = 12) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    for index in range(rows):
        y = 100.0 + index * 14.0
        page.insert_text((50, y), f"LEFT column line {index}", fontsize=9)
        page.insert_text((320, y), f"RIGHT column line {index}", fontsize=9)
    data = document.tobytes()
    document.close()
    return data
