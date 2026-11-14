"""HTTP surface of the cvs module: upload, list, Parser View data."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, File, Form, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from app.shared.errors import AppError

if TYPE_CHECKING:
    from app.container import Container

router = APIRouter(prefix="/api", tags=["cvs"])

READ_CHUNK = 64 * 1024


class CvCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1, max_length=60)
    target_role: str | None = Field(default=None, max_length=120)


class CvOut(BaseModel):
    id: str
    label: str
    target_role: str | None = None


class CvListItem(BaseModel):
    id: str
    label: str
    target_role: str | None = None
    created_at: datetime
    version_count: int
    latest_version_id: str | None = None


class CvListOut(BaseModel):
    items: list[CvListItem]
    total: int


class VersionOut(BaseModel):
    id: str
    cv_id: str
    version_no: int
    note: str | None = None
    file_name: str
    file_sha256: str
    text_sha256: str
    uploaded_at: datetime
    warnings: list[str]
    sections: list[str]
    redaction: dict[str, int]
    redacted_chars: int


class ParserViewOut(VersionOut):
    text: str
    section_texts: dict[str, str]


class ImpactOut(BaseModel):
    cv_id: str
    version_count: int
    analysis_count: int


def _container(request: Request) -> Container:
    return request.app.state.container


async def _read_upload(upload: UploadFile, limit: int) -> bytes:
    """Read in chunks so an oversized upload is stopped, not buffered."""
    chunks: list[bytes] = []
    size = 0
    while chunk := await upload.read(READ_CHUNK):
        size += len(chunk)
        if size > limit:
            raise AppError(
                "UPLOAD_TOO_LARGE",
                "The file exceeds the upload limit.",
                {"limit_bytes": limit, "size_bytes": size},
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/cvs", status_code=status.HTTP_201_CREATED, response_model=CvOut)
def create_cv(payload: CvCreate, request: Request) -> dict[str, Any]:
    return _container(request).cvs.create(label=payload.label, target_role=payload.target_role)


@router.get("/cvs", response_model=CvListOut)
def list_cvs(request: Request) -> dict[str, Any]:
    return _container(request).cvs.list_all()


@router.post(
    "/cvs/{cv_id}/versions",
    status_code=status.HTTP_201_CREATED,
    response_model=VersionOut,
    responses={409: {"description": "Identical file already uploaded"}},
)
async def add_version(
    cv_id: str,
    request: Request,
    file: Annotated[UploadFile, File()],
    note: Annotated[str | None, Form()] = None,
) -> dict[str, Any]:
    container = _container(request)
    data = await _read_upload(file, container.settings.upload_max_bytes)
    return container.cvs.add_version(
        cv_id,
        file_name=file.filename or "upload",
        data=data,
        note=note,
    )


@router.get("/cv-versions/{version_id}", response_model=VersionOut)
def read_version(version_id: str, request: Request) -> dict[str, Any]:
    return _container(request).cvs.version(version_id)


@router.get("/cv-versions/{version_id}/parser-view", response_model=ParserViewOut)
def read_parser_view(version_id: str, request: Request) -> dict[str, Any]:
    return _container(request).cvs.parser_view(version_id)


@router.get("/cvs/{cv_id}/impact", response_model=ImpactOut)
def read_impact(cv_id: str, request: Request) -> dict[str, Any]:
    return _container(request).cvs.impact(cv_id)
