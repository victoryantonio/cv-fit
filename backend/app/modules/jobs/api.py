"""HTTP surface of the jobs module: manual jobs, triage and JD snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Annotated, Any

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.container import Container

router = APIRouter(prefix="/api", tags=["jobs"])

MAX_TITLE_CHARS = 200


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE_CHARS)
    company: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=1000)


class JobPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = None
    outcome: str | None = None
    applied_at: datetime | None = None
    keep: bool | None = Field(
        default=None, description="Clear the pre-filter reason so the job is kept."
    )


class JobOut(BaseModel):
    id: str
    source: str
    title: str
    company: str | None = None
    location: str | None = None
    url: str | None = None
    status: str
    outcome: str
    applied_at: datetime | None = None
    filter_reason: str | None = None
    received_at: datetime | None = None
    created_at: datetime


class JobListItem(JobOut):
    snapshot_count: int
    latest_snapshot_id: str | None = None


class JobListOut(BaseModel):
    items: list[JobListItem]
    total: int


class SnapshotOut(BaseModel):
    id: str
    source_kind: str
    text_sha256: str
    chars: int
    injection_flags: list[str]
    truncation_warning: bool
    truncation_reasons: list[str]
    captured_at: datetime


class SnapshotCreateOut(SnapshotOut):
    reused: bool


class SnapshotDetailOut(SnapshotOut):
    job_id: str
    raw_text: str


class JobDetailOut(JobOut):
    snapshots: list[SnapshotOut]


class SnapshotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str
    source_kind: str = "page_paste"


class SyncAlertsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    since: datetime | None = None
    limit: int = Field(default=25, ge=1, le=50)


class SyncAlertsOut(BaseModel):
    messages: int
    new: int
    duplicate: int
    filtered: int
    parse_failed: list[str]
    synced_at: datetime | None = None


class SyncStatusOut(BaseModel):
    source: str
    synced_at: datetime | None = None


def _container(request: Request) -> Container:
    return request.app.state.container


@router.post("/jobs", status_code=status.HTTP_201_CREATED, response_model=JobOut)
def create_job(payload: JobCreate, request: Request) -> dict[str, Any]:
    return _container(request).jobs.create(
        title=payload.title,
        company=payload.company,
        url=payload.url,
        location=payload.location,
    )


@router.get("/jobs", response_model=JobListOut)
def list_jobs(
    request: Request,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    filtered: Annotated[bool | None, Query()] = None,
) -> dict[str, Any]:
    return _container(request).jobs.list(status=status_filter, filtered=filtered)


@router.post("/jobs/sync-alerts", response_model=SyncAlertsOut)
async def sync_alerts(payload: SyncAlertsIn, request: Request) -> dict[str, Any]:
    """Read alert emails through the Gmail helper; nothing is fetched from LinkedIn."""
    return await _container(request).jobs.sync_alerts(since=payload.since, limit=payload.limit)


@router.get("/jobs/sync-status", response_model=SyncStatusOut)
def read_sync_status(request: Request) -> dict[str, Any]:
    """When alerts were last pulled; null before the first sync."""
    return _container(request).jobs.last_sync()


@router.get("/jobs/{job_id}", response_model=JobDetailOut)
def read_job(job_id: str, request: Request) -> dict[str, Any]:
    return _container(request).jobs.get(job_id)


@router.patch("/jobs/{job_id}", response_model=JobOut)
def patch_job(job_id: str, payload: JobPatch, request: Request) -> dict[str, Any]:
    return _container(request).jobs.update(
        job_id,
        status=payload.status,
        outcome=payload.outcome,
        applied_at=payload.applied_at,
        keep=payload.keep,
    )


@router.post(
    "/jobs/{job_id}/snapshots",
    status_code=status.HTTP_201_CREATED,
    response_model=SnapshotCreateOut,
)
def create_snapshot(job_id: str, payload: SnapshotCreate, request: Request) -> dict[str, Any]:
    return _container(request).jobs.add_snapshot(
        job_id,
        raw_text=payload.raw_text,
        source_kind=payload.source_kind,
    )


@router.get("/jd-snapshots/{snapshot_id}", response_model=SnapshotDetailOut)
def read_snapshot(snapshot_id: str, request: Request) -> dict[str, Any]:
    return _container(request).jobs.snapshot(snapshot_id)
