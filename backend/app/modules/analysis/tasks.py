"""The analysis task queue: one persisted row per unit of work.

One worker, one database. Every transition is a short transaction, and no
transaction is held open while a model call is in flight, so a poll request
never waits behind the pipeline.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.modules.analysis import queries
from app.modules.analysis.enums import Step, TaskKind, TaskStatus
from app.modules.analysis.models import AnalysisTask
from app.shared.clock import Clock
from app.shared.errors import AppError


def as_payload(task: AnalysisTask) -> dict[str, Any]:
    params = task.params or {}
    return {
        "id": task.id,
        "kind": task.kind,
        "status": task.status,
        "current_step": task.current_step,
        "attempts": task.attempts,
        "error_code": task.error_code,
        "analysis_id": task.analysis_id,
        "cache_key": params.get("cache_key"),
        "cancel_requested": task.cancel_requested,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
    }


def _as_utc(value: datetime) -> datetime:
    """SQLite hands back naive datetimes; treat them as UTC before comparing."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class EnqueueResult:
    cache_hit: bool
    cache_key: str
    task_id: str | None = None
    analysis_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "cache_hit": self.cache_hit,
            "cache_key": self.cache_key,
            "task_id": self.task_id,
            "analysis_id": self.analysis_id,
        }


@dataclass(frozen=True, slots=True)
class TaskService:
    """Enqueue, claim, report a step, and land a terminal status."""

    session_factory: sessionmaker[Session]
    clock: Clock
    budget_monthly: Callable[[], int]
    probe: Callable[..., dict[str, Any]]

    def enqueue(
        self,
        *,
        cv_version_id: str,
        snapshot_id: str,
        force: bool = False,
        override_budget: bool = False,
    ) -> EnqueueResult:
        """A cache hit answers immediately; a miss becomes one queued task."""
        found = self.probe(cv_version_id=cv_version_id, snapshot_id=snapshot_id)
        key = str(found["cache_key"])
        cached_id = found["analysis_id"]
        if cached_id is not None and not force:
            return EnqueueResult(cache_hit=True, cache_key=key, analysis_id=str(cached_id))
        self._check_budget(override=override_budget)
        with self.session_factory() as session:
            # A second click on the same packet joins the task already waiting.
            existing = queries.queued_task_for_key(session, key)
            if existing is not None:
                return EnqueueResult(cache_hit=False, cache_key=key, task_id=existing.id)
            now = self.clock.now()
            task = AnalysisTask(
                kind=TaskKind.ANALYZE,
                params={
                    "cv_version_id": cv_version_id,
                    "snapshot_id": snapshot_id,
                    "cache_key": key,
                    "force": force,
                },
                status=TaskStatus.QUEUED,
                created_at=now,
                updated_at=now,
            )
            session.add(task)
            session.commit()
            return EnqueueResult(cache_hit=False, cache_key=key, task_id=task.id)

    def get(self, task_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            return as_payload(self._load(session, task_id))

    def params(self, task_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            return dict(self._load(session, task_id).params or {})

    def recent(self, *, limit: int = 20) -> list[dict[str, Any]]:
        with self.session_factory() as session:
            return [as_payload(task) for task in queries.recent_tasks(session, limit)]

    def claim_next(self) -> str | None:
        """Claim the oldest queued task. Nothing else may claim it afterwards."""
        with self.session_factory() as session:
            task = queries.next_queued_task(session)
            if task is None:
                return None
            if task.cancel_requested:
                task.status = TaskStatus.CANCELLED
                task.finished_at = self.clock.now()
                session.commit()
                return None
            self._mark_running(task)
            session.commit()
            return task.id

    def start(self, task_id: str) -> dict[str, Any]:
        """Explicit start for a task driven by a test or the CLI."""
        with self.session_factory() as session:
            task = self._load(session, task_id)
            if task.status == TaskStatus.RUNNING:
                return as_payload(task)
            if task.status != TaskStatus.QUEUED:
                raise AppError(
                    "CONFLICT",
                    "Only a queued task can start.",
                    {"task_id": task_id, "status": task.status},
                )
            self._mark_running(task)
            session.commit()
            return as_payload(task)

    def set_step(self, task_id: str, step: str) -> None:
        with self.session_factory() as session:
            task = queries.get_task(session, task_id)
            if task is None or task.status != TaskStatus.RUNNING:
                return
            task.current_step = step
            session.commit()

    def cancel_pending(self, task_id: str) -> bool:
        """Read fresh from the database: the cancel may come from another request."""
        with self.session_factory() as session:
            task = queries.get_task(session, task_id)
            return bool(task is not None and task.cancel_requested)

    def cancel(self, task_id: str) -> dict[str, Any]:
        """A queued task stops now; a running one stops at its next step boundary."""
        with self.session_factory() as session:
            task = self._load(session, task_id)
            if task.status in (TaskStatus.OK, TaskStatus.FAILED, TaskStatus.CANCELLED):
                return as_payload(task)
            task.cancel_requested = True
            if task.status == TaskStatus.QUEUED:
                task.status = TaskStatus.CANCELLED
                task.finished_at = self.clock.now()
            session.commit()
            return as_payload(task)

    def succeed(self, task_id: str, *, analysis_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            task = self._load(session, task_id)
            task.status = TaskStatus.OK
            task.analysis_id = analysis_id
            task.current_step = Step.S9_PERSIST
            task.error_code = None
            task.finished_at = self.clock.now()
            session.commit()
            return as_payload(task)

    def fail(self, task_id: str, *, code: str) -> dict[str, Any]:
        with self.session_factory() as session:
            task = self._load(session, task_id)
            task.status = TaskStatus.FAILED
            task.error_code = code
            task.finished_at = self.clock.now()
            session.commit()
            return as_payload(task)

    def mark_cancelled(self, task_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            task = self._load(session, task_id)
            task.status = TaskStatus.CANCELLED
            task.cancel_requested = True
            task.finished_at = self.clock.now()
            session.commit()
            return as_payload(task)

    def release(self, task_id: str) -> dict[str, Any]:
        """Shutdown in the middle of a task: hand it back to the queue."""
        with self.session_factory() as session:
            task = self._load(session, task_id)
            if task.status != TaskStatus.RUNNING:
                return as_payload(task)
            task.status = TaskStatus.QUEUED
            task.current_step = None
            task.started_at = None
            session.commit()
            return as_payload(task)

    def retry(self, task_id: str) -> dict[str, Any]:
        """E17: a failed or cancelled task can be queued again."""
        with self.session_factory() as session:
            task = self._load(session, task_id)
            if task.status not in (TaskStatus.FAILED, TaskStatus.CANCELLED):
                raise AppError(
                    "CONFLICT",
                    "Only a failed or cancelled task can be requeued.",
                    {"task_id": task_id, "status": task.status},
                )
            task.status = TaskStatus.QUEUED
            task.cancel_requested = False
            task.error_code = None
            task.current_step = None
            task.started_at = None
            task.finished_at = None
            session.commit()
            return as_payload(task)

    def recover_stale(self, timeout_seconds: int) -> int:
        """Anything left running past the timeout belongs to a dead process."""
        cutoff = self.clock.now() - timedelta(seconds=timeout_seconds)
        with self.session_factory() as session:
            stale = [
                task
                for task in queries.running_tasks(session)
                if _as_utc(task.started_at or task.created_at) <= cutoff
            ]
            for task in stale:
                task.status = TaskStatus.QUEUED
                task.current_step = None
                task.started_at = None
                task.error_code = "TASK_STALE"
            session.commit()
            return len(stale)

    def month_tokens(self) -> int:
        now = self.clock.now()
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        with self.session_factory() as session:
            return queries.tokens_since(session, start)

    def _check_budget(self, *, override: bool) -> None:
        """NFR-10: a spent budget blocks new work unless overridden explicitly."""
        limit = self.budget_monthly()
        if override or limit <= 0:
            return
        used = self.month_tokens()
        if used >= limit:
            raise AppError(
                "BUDGET_EXCEEDED",
                "This month's token budget is spent. Override it explicitly to run anyway.",
                {"limit": limit, "used": used},
            )

    def _mark_running(self, task: AnalysisTask) -> None:
        task.status = TaskStatus.RUNNING
        task.started_at = self.clock.now()
        task.current_step = Step.S0_PREFLIGHT
        task.attempts += 1

    @staticmethod
    def _load(session: Session, task_id: str) -> AnalysisTask:
        task = queries.get_task(session, task_id)
        if task is None:
            raise AppError("NOT_FOUND", "That task does not exist.", {"task_id": task_id})
        return task
