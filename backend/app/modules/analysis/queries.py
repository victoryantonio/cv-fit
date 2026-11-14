"""Reads for the analysis module. No business rules live here."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.analysis.enums import TaskStatus
from app.modules.analysis.models import (
    Analysis,
    AnalysisTask,
    JdExtraction,
    JdRequirement,
    LlmCall,
    RequirementMatch,
    Suggestion,
)


def get_analysis(session: Session, analysis_id: str) -> Analysis | None:
    return session.get(Analysis, analysis_id)


def get_analysis_by_key(session: Session, cache_key: str) -> Analysis | None:
    return session.scalars(select(Analysis).where(Analysis.cache_key == cache_key)).first()


def get_extraction(session: Session, extraction_id: str) -> JdExtraction | None:
    return session.get(JdExtraction, extraction_id)


def get_requirement(session: Session, requirement_id: str) -> JdRequirement | None:
    return session.get(JdRequirement, requirement_id)


def list_requirements(
    session: Session, extraction_id: str, *, active_only: bool
) -> list[JdRequirement]:
    statement = select(JdRequirement).where(JdRequirement.extraction_id == extraction_id)
    if active_only:
        statement = statement.where(JdRequirement.active.is_(True))
    return list(session.scalars(statement.order_by(JdRequirement.position)))


def list_matches(session: Session, analysis_id: str) -> list[RequirementMatch]:
    statement = select(RequirementMatch).where(RequirementMatch.analysis_id == analysis_id)
    return list(session.scalars(statement))


def get_suggestion(session: Session, suggestion_id: str) -> Suggestion | None:
    return session.get(Suggestion, suggestion_id)


def list_suggestions(session: Session, analysis_id: str) -> list[Suggestion]:
    statement = (
        select(Suggestion)
        .where(Suggestion.analysis_id == analysis_id)
        .order_by(Suggestion.guard_status, Suggestion.type)
    )
    return list(session.scalars(statement))


def analyses_for_requirement(session: Session, requirement_id: str) -> list[str]:
    statement = (
        select(RequirementMatch.analysis_id)
        .where(RequirementMatch.requirement_id == requirement_id)
        .distinct()
    )
    return list(session.scalars(statement))


def analyses_for_snapshots(session: Session, snapshot_ids: Sequence[str]) -> list[Analysis]:
    """Every analysis over these JD snapshots, newest first."""
    if not snapshot_ids:
        return []
    statement = (
        select(Analysis)
        .join(JdExtraction, JdExtraction.id == Analysis.extraction_id)
        .where(JdExtraction.jd_snapshot_id.in_(list(snapshot_ids)))
        .order_by(Analysis.created_at.desc())
    )
    return list(session.scalars(statement))


def get_task(session: Session, task_id: str) -> AnalysisTask | None:
    return session.get(AnalysisTask, task_id)


def next_queued_task(session: Session) -> AnalysisTask | None:
    statement = (
        select(AnalysisTask)
        .where(AnalysisTask.status == TaskStatus.QUEUED)
        .order_by(AnalysisTask.created_at)
        .limit(1)
    )
    return session.scalars(statement).first()


def running_tasks(session: Session) -> list[AnalysisTask]:
    statement = select(AnalysisTask).where(AnalysisTask.status == TaskStatus.RUNNING)
    return list(session.scalars(statement))


def recent_tasks(session: Session, limit: int) -> list[AnalysisTask]:
    statement = select(AnalysisTask).order_by(AnalysisTask.created_at.desc()).limit(limit)
    return list(session.scalars(statement))


def queued_task_for_key(session: Session, cache_key: str) -> AnalysisTask | None:
    """Filtered in Python: `params` is JSON and the dialect may be swapped later.

    The queued set is tiny by construction (one worker, one user).
    """
    statement = select(AnalysisTask).where(AnalysisTask.status == TaskStatus.QUEUED)
    for task in session.scalars(statement):
        if (task.params or {}).get("cache_key") == cache_key:
            return task
    return None


def tokens_since(session: Session, since: datetime) -> int:
    """Total stored tokens at or after `since`. Content is never involved."""
    statement = select(func.coalesce(func.sum(LlmCall.tokens_in + LlmCall.tokens_out), 0)).where(
        LlmCall.created_at >= since
    )
    return int(session.scalar(statement) or 0)


def calls_for_analysis(session: Session, analysis_id: str) -> list[LlmCall]:
    statement = select(LlmCall).where(LlmCall.analysis_id == analysis_id)
    return list(session.scalars(statement.order_by(LlmCall.created_at)))
