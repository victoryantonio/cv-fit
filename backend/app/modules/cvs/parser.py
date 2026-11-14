"""CV text extraction. PDF and DOCX only.

The parser reports problems as warnings; it never blocks an upload. A warning is
what the Parser View shows next to the redacted preview (E02, E04).
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any, Final, Protocol

SECTION_KEYS: Final = (
    "summary",
    "experience",
    "education",
    "skills",
    "projects",
    "certifications",
    "other",
)

SHORT_TEXT_CHARS: Final = 300
NO_TEXT_LAYER_CHARS: Final = 20

_HEADERS: Final[dict[str, tuple[str, ...]]] = {
    "summary": (
        "summary",
        "professional summary",
        "profile",
        "professional profile",
        "objective",
        "about me",
        "ringkasan",
        "tentang saya",
    ),
    "experience": (
        "experience",
        "work experience",
        "professional experience",
        "employment",
        "employment history",
        "work history",
        "pengalaman",
        "pengalaman kerja",
    ),
    "education": ("education", "pendidikan", "riwayat pendidikan", "academic"),
    "skills": ("skills", "technical skills", "core skills", "keahlian", "kemampuan"),
    "projects": ("projects", "selected projects", "proyek", "portfolio"),
    "certifications": (
        "certifications",
        "certificates",
        "licenses",
        "sertifikasi",
        "pelatihan",
        "training",
    ),
    "other": (
        "languages",
        "bahasa",
        "awards",
        "honors",
        "publications",
        "volunteer",
        "interests",
        "references",
    ),
}

_BLANK_RUN: Final = re.compile(r"\n{3,}")


class DocumentParseError(Exception):
    """The document could not be read at all. The caller maps it to an error code."""


@dataclass(frozen=True, slots=True)
class ParsedCv:
    text: str
    sections: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    kind: str = "unknown"
    page_count: int | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "sections": self.sections,
            "warnings": self.warnings,
            "kind": self.kind,
            "page_count": self.page_count,
        }


class DocumentParser(Protocol):
    def parse(self, data: bytes, *, file_name: str) -> ParsedCv: ...


def _normalise(lines: Iterable[str]) -> str:
    cleaned = [line.rstrip() for line in lines]
    return _BLANK_RUN.sub("\n\n", "\n".join(cleaned)).strip("\n")


def _header_key(line: str) -> str | None:
    stripped = line.strip().rstrip(":").strip()
    if not 2 <= len(stripped) <= 46:
        return None
    lowered = re.sub(r"\s+", " ", stripped.lower())
    for key, headers in _HEADERS.items():
        for header in headers:
            if lowered == header or lowered.startswith(f"{header} "):
                return key
    return None


def split_sections(text: str) -> dict[str, str]:
    """Line-based header detection. Headings before the first match go to `other`."""
    buckets: dict[str, list[str]] = {key: [] for key in SECTION_KEYS}
    current = "other"
    for line in text.split("\n"):
        key = _header_key(line)
        if key is not None:
            current = key
        buckets[current].append(line)
    sections: dict[str, str] = {}
    for key in SECTION_KEYS:
        body = _normalise(buckets[key])
        if body:
            sections[key] = body
    return sections


def _multi_column_suspected(words: Sequence[Sequence[Any]], page_width: float) -> bool:
    """A wide, repeated gap inside a line means the page holds columns.

    Block geometry cannot carry this signal: PyMuPDF merges side-by-side columns
    into a single block and simply interleaves their lines. Words keep their own
    coordinates, so the gap between two word clusters is still visible.
    A wrong guess only produces a warning, so a coarse test is enough.
    """
    if page_width <= 0 or not words:
        return False
    min_gap = 0.15 * page_width
    lines: dict[float, list[tuple[float, float]]] = {}
    for word in words:
        x0, y0, x1, y1 = (float(value) for value in word[:4])
        lines.setdefault(round((y0 + y1) / 2, 1), []).append((x0, x1))
    gapped = 0
    for boxes in lines.values():
        boxes.sort()
        for index in range(len(boxes) - 1):
            if boxes[index + 1][0] - boxes[index][1] > min_gap:
                gapped += 1
                break
    return len(lines) >= 3 and gapped >= 0.4 * len(lines)


def parse_pdf(data: bytes) -> ParsedCv:
    try:
        import pymupdf
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise DocumentParseError("pymupdf is not installed") from exc

    try:
        document = pymupdf.open(stream=data, filetype="pdf")
    except Exception as exc:
        raise DocumentParseError("not a readable PDF") from exc

    pages: list[str] = []
    columns = False
    try:
        for page_number in range(document.page_count):
            page = document.load_page(page_number)
            pages.append(str(page.get_text()))
            if not columns:
                columns = _multi_column_suspected(page.get_text("words"), float(page.rect.width))
        page_count = int(document.page_count)
    finally:
        document.close()

    text = _normalise(pages)
    sections = split_sections(text)
    warnings = _report(text, sections, kind="pdf", has_text_layer=len(text) >= NO_TEXT_LAYER_CHARS)
    if columns:
        warnings.insert(1, "multi_column_suspected")
    return ParsedCv(
        text=text,
        sections=sections,
        warnings=warnings,
        kind="pdf",
        page_count=page_count,
    )


def parse_docx(data: bytes) -> ParsedCv:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover - dependency is pinned
        raise DocumentParseError("python-docx is not installed") from exc

    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise DocumentParseError("not a readable DOCX") from exc

    lines = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            lines.append(" | ".join(cell.text.strip() for cell in row.cells))

    text = _normalise(lines)
    sections = split_sections(text)
    warnings = _report(text, sections, kind="docx", has_text_layer=True)
    return ParsedCv(text=text, sections=sections, warnings=warnings, kind="docx")


def _report(text: str, sections: dict[str, str], *, kind: str, has_text_layer: bool) -> list[str]:
    warnings: list[str] = []
    if not has_text_layer:
        warnings.append("no_text_layer")
    if len(text) < SHORT_TEXT_CHARS:
        warnings.append("text_short")
    if kind == "pdf" and not text:
        warnings.append("empty_document")
    if text and not any(key != "other" for key in sections):
        warnings.append("no_sections_detected")
    return warnings


def parse_document(data: bytes, *, file_name: str) -> ParsedCv:
    suffix = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if suffix == "pdf":
        return parse_pdf(data)
    if suffix == "docx":
        return parse_docx(data)
    raise DocumentParseError(f"unsupported extension: {suffix or 'none'}")
