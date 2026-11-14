"""HTTP surface of the analysis module: run a packet, read it, adjust requirements."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.modules.analysis.api_models import (
    AnalysisCreate,
    AnalysisOut,
    AnalysisQueuedOut,
    AnalysisRunOut,
    CoverNotePatch,
    HistoryOut,
    RequirementPatch,
    RequirementPatchOut,
    SuggestionPatch,
    SuggestionPatchOut,
    TaskOut,
)
from app.modules.analysis.export import render_markdown

if TYPE_CHECKING:
    from app.container import Container

router = APIRouter(prefix="/api", tags=["analysis"])


def _container(request: Request) -> Container:
    return request.app.state.container


@router.post(
    "/analyses",
    response_model=AnalysisRunOut,
    responses={status.HTTP_202_ACCEPTED: {"model": AnalysisQueuedOut}},
)
def create_analysis(payload: AnalysisCreate, request: Request) -> Any:
    """200 with the stored packet on a cache hit, 202 with a task id on a miss."""
    container = _container(request)
    queued = container.tasks.enqueue(
        cv_version_id=payload.cv_version_id,
        snapshot_id=payload.snapshot_id,
        force=payload.force,
        override_budget=payload.override_budget,
    )
    if queued.cache_hit:
        return {**container.analysis.get(str(queued.analysis_id)), "cache_hit": True}
    body = AnalysisQueuedOut(
        task=TaskOut.model_validate(container.tasks.get(str(queued.task_id))),
        cache_key=queued.cache_key,
    )
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content=body.model_dump(mode="json"))


@router.get("/tasks", response_model=list[TaskOut])
def list_tasks(
    request: Request, limit: int = Query(default=20, ge=1, le=100)
) -> list[dict[str, Any]]:
    return _container(request).tasks.recent(limit=limit)


@router.get("/tasks/{task_id}", response_model=TaskOut)
def read_task(task_id: str, request: Request) -> dict[str, Any]:
    return _container(request).tasks.get(task_id)


@router.post("/tasks/{task_id}/cancel", response_model=TaskOut)
def cancel_task(task_id: str, request: Request) -> dict[str, Any]:
    return _container(request).tasks.cancel(task_id)


@router.post("/tasks/{task_id}/retry", response_model=TaskOut)
def retry_task(task_id: str, request: Request) -> dict[str, Any]:
    return _container(request).tasks.retry(task_id)


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def read_analysis(
    analysis_id: str, request: Request, include_rejected: bool = False
) -> dict[str, Any]:
    return _container(request).analysis.get(analysis_id, include_rejected=include_rejected)


@router.patch("/suggestions/{suggestion_id}", response_model=SuggestionPatchOut)
def patch_suggestion(
    suggestion_id: str, payload: SuggestionPatch, request: Request
) -> dict[str, Any]:
    return _container(request).analysis.set_suggestion_decision(
        suggestion_id, decision=payload.decision, reason=payload.reason
    )


@router.patch("/requirements/{requirement_id}", response_model=RequirementPatchOut)
def patch_requirement(
    requirement_id: str, payload: RequirementPatch, request: Request
) -> dict[str, Any]:
    return _container(request).analysis.set_requirement_active(
        requirement_id, active=payload.active
    )


@router.get("/jobs/{job_id}/history", response_model=HistoryOut)
def read_history(job_id: str, request: Request) -> dict[str, Any]:
    return _container(request).analysis.history(job_id)


@router.patch("/analyses/{analysis_id}/cover-note", response_model=AnalysisOut)
def patch_cover_note(analysis_id: str, payload: CoverNotePatch, request: Request) -> dict[str, Any]:
    return _container(request).analysis.set_cover_note_edited(analysis_id, text=payload.text)


@router.post("/analyses/{analysis_id}/cover-note/regenerate", response_model=AnalysisOut)
async def regenerate_cover_note(analysis_id: str, request: Request) -> dict[str, Any]:
    return await _container(request).analysis.regenerate_cover_note(analysis_id)


@router.get("/analyses/{analysis_id}/export.md", response_model=None)
def export_analysis(analysis_id: str, request: Request) -> Response:
    payload = _container(request).analysis.get(analysis_id)
    return Response(content=render_markdown(payload), media_type="text/markdown")

