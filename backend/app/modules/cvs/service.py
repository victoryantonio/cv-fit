"""CV intake: validate the upload, parse it out of process, redact, then store.

Order matters. Nothing is written until the document has parsed and the text is
non-empty, so a failed parse leaves no half-stored version behind (E03).
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.modules.cvs import queries
from app.modules.cvs.models import CV, CVVersion
from app.modules.cvs.parser import DocumentParseError, DocumentParser, ParsedCv
from app.modules.cvs.redactor import RedactionResult, redact
from app.shared.clock import Clock
from app.shared.errors import AppError

MAX_LABEL_CHARS: Final = 60
ALLOWED_EXTENSIONS: Final = {"pdf": ".pdf", "docx": ".docx"}
PDF_MAGIC: Final = b"%PDF-"
ZIP_MAGIC: Final = b"PK\x03\x04"


def detect_kind(file_name: str, data: bytes) -> str:
    """Extension and magic bytes must agree. Either one alone is spoofable."""
    suffix = Path(file_name).suffix.lower()
    kind = next((name for name, ext in ALLOWED_EXTENSIONS.items() if ext == suffix), None)
    if kind is None:
        raise AppError(
            "UPLOAD_INVALID",
            "Only PDF and DOCX files are accepted.",
            {"reason": "extension", "extension": suffix or None},
        )
    if kind == "pdf" and not data.startswith(PDF_MAGIC):
        raise AppError("UPLOAD_INVALID", "This file is not a PDF.", {"reason": "magic_bytes"})
    if kind == "docx" and not _is_docx(data):
        raise AppError("UPLOAD_INVALID", "This file is not a DOCX.", {"reason": "magic_bytes"})
    return kind


def _is_docx(data: bytes) -> bool:
    if not data.startswith(ZIP_MAGIC):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return "word/document.xml" in archive.namelist()
    except zipfile.BadZipFile:
        return False


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _require_cv(session: Session, cv_id: str) -> None:
    if queries.get_cv(session, cv_id) is None:
        raise AppError("NOT_FOUND", "That CV does not exist.", {"cv_id": cv_id})


def _require_new_file(session: Session, cv_id: str, file_sha256: str) -> None:
    """The same bytes twice is a re-upload, not a new version."""
    existing = queries.find_version_by_file_sha(session, cv_id, file_sha256)
    if existing is None:
        return
    raise AppError(
        "CONFLICT",
        "This file is already uploaded as an earlier version.",
        {
            "version_id": existing.id,
            "version_no": existing.version_no,
            "href": f"/api/cv-versions/{existing.id}",
        },
    )


def _version_row(
    *,
    cv_id: str,
    version_no: int,
    note: str | None,
    file_name: str,
    file_sha256: str,
    parsed: ParsedCv,
    redaction: RedactionResult,
    stored_path: Path,
    uploaded_at: Any,
) -> CVVersion:
    """The row is built from the parse result only, so nothing half-stored exists."""
    return CVVersion(
        cv_id=cv_id,
        version_no=version_no,
        note=(note or None),
        file_name=Path(file_name).name,
        file_sha256=file_sha256,
        text_sha256=_digest(redaction.text.encode("utf-8")),
        raw_text=parsed.text,
        redacted_text=redaction.text,
        structured=parsed.sections,
        parser_report={
            "warnings": parsed.warnings,
            "kind": parsed.kind,
            "page_count": parsed.page_count,
            "redaction": redaction.counts,
            "redacted_chars": len(redaction.text),
            "raw_chars": len(parsed.text),
            "stored_path": str(stored_path),
        },
        uploaded_at=uploaded_at,
    )


@dataclass(frozen=True, slots=True)
class CvService:
    session_factory: sessionmaker[Session]
    settings: Settings
    clock: Clock
    parser: DocumentParser

    def create(self, *, label: str, target_role: str | None = None) -> dict[str, Any]:
        cleaned = label.strip()
        if not cleaned or len(cleaned) > MAX_LABEL_CHARS:
            raise AppError(
                "VALIDATION_ERROR",
                f"A label of 1 to {MAX_LABEL_CHARS} characters is required.",
                {"field": "label"},
            )
        with self.session_factory() as session:
            cv = CV(label=cleaned, target_role=(target_role or None), created_at=self.clock.now())
            session.add(cv)
            session.commit()
            return {"id": cv.id, "label": cv.label, "target_role": cv.target_role}

    def list_all(self) -> dict[str, Any]:
        with self.session_factory() as session:
            items = [
                {
                    "id": summary.id,
                    "label": summary.label,
                    "target_role": summary.target_role,
                    "created_at": summary.created_at,
                    "version_count": summary.version_count,
                    "latest_version_id": summary.latest_version_id,
                }
                for summary in queries.list_cvs(session)
            ]
        return {"items": items, "total": len(items)}

    def add_version(
        self,
        cv_id: str,
        *,
        file_name: str,
        data: bytes,
        note: str | None = None,
    ) -> dict[str, Any]:
        self._check_upload(data)
        kind = detect_kind(file_name, data)
        file_sha256 = _digest(data)

        with self.session_factory() as session:
            _require_cv(session, cv_id)
            _require_new_file(session, cv_id, file_sha256)
            parsed = self._parse(data, file_name=file_name)
            redaction = redact(parsed.text, custom_terms=self.settings.redaction_terms)
            if not redaction.text.strip():
                raise AppError(
                    "CV_PARSE_LOW_YIELD",
                    "No text could be read from this file.",
                    {"warnings": parsed.warnings},
                )
            version = _version_row(
                cv_id=cv_id,
                version_no=queries.next_version_no(session, cv_id),
                note=note,
                file_name=file_name,
                file_sha256=file_sha256,
                parsed=parsed,
                redaction=redaction,
                stored_path=self._store_file(file_sha256, kind, data),
                uploaded_at=self.clock.now(),
            )
            session.add(version)
            session.commit()
            return self._version_payload(version, include_text=False)

    def _check_upload(self, data: bytes) -> None:
        if not data:
            raise AppError("UPLOAD_INVALID", "The uploaded file is empty.", {"reason": "empty"})
        if len(data) > self.settings.upload_max_bytes:
            raise AppError(
                "UPLOAD_TOO_LARGE",
                "The file exceeds the upload limit.",
                {"limit_bytes": self.settings.upload_max_bytes, "size_bytes": len(data)},
            )

    def version(self, version_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            version = queries.get_version(session, version_id)
            if version is None:
                raise AppError(
                    "NOT_FOUND", "That CV version does not exist.", {"version_id": version_id}
                )
            return self._version_payload(version, include_text=False)

    def parser_view(self, version_id: str) -> dict[str, Any]:
        """The stored redacted text, unchanged. This is what an LLM would receive."""
        with self.session_factory() as session:
            version = queries.get_version(session, version_id)
            if version is None:
                raise AppError(
                    "NOT_FOUND", "That CV version does not exist.", {"version_id": version_id}
                )
            return self._version_payload(version, include_text=True)

    def impact(self, cv_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            if queries.get_cv(session, cv_id) is None:
                raise AppError("NOT_FOUND", "That CV does not exist.", {"cv_id": cv_id})
            versions = queries.list_versions(session, cv_id)
            version_ids = [version.id for version in versions]
            return {
                "cv_id": cv_id,
                "version_count": len(versions),
                "analysis_count": queries.count_analyses_for_versions(session, version_ids),
            }

    def _parse(self, data: bytes, *, file_name: str) -> ParsedCv:
        try:
            return self.parser.parse(data, file_name=file_name)
        except DocumentParseError as exc:
            raise AppError(
                "CV_PARSE_FAILED",
                "This file could not be read. Try exporting it again.",
                {"reason": str(exc)},
            ) from exc

    def _store_file(self, file_sha256: str, kind: str, data: bytes) -> Path:
        directory = self.settings.data_dir / "uploads"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{file_sha256}{ALLOWED_EXTENSIONS[kind]}"
        if not path.exists():
            path.write_bytes(data)
        return path

    @staticmethod
    def _version_payload(version: CVVersion, *, include_text: bool) -> dict[str, Any]:
        report = version.parser_report or {}
        payload: dict[str, Any] = {
            "id": version.id,
            "cv_id": version.cv_id,
            "version_no": version.version_no,
            "note": version.note,
            "file_name": version.file_name,
            "file_sha256": version.file_sha256,
            "text_sha256": version.text_sha256,
            "uploaded_at": version.uploaded_at,
            "warnings": report.get("warnings", []),
            "sections": sorted((version.structured or {}).keys()),
            "redaction": report.get("redaction", {}),
            "redacted_chars": report.get("redacted_chars", len(version.redacted_text)),
        }
        if include_text:
            payload["text"] = version.redacted_text
            payload["section_texts"] = version.structured or {}
        return payload
