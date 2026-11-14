"""The single in-process worker that drains the analysis queue.

One task at a time, on purpose: a task is already concurrent inside itself (the
match runs), so a second worker would only add write contention on SQLite.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.modules.analysis.service import AnalysisService, PipelineCancelled
from app.modules.analysis.tasks import TaskService
from app.shared.errors import AppError
from app.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Worker:
    analysis: AnalysisService
    tasks: TaskService
    poll_seconds: float
    stale_seconds: int

    def recover(self) -> int:
        """Called once at startup, before the loop takes anything new."""
        count = self.tasks.recover_stale(self.stale_seconds)
        if count:
            logger.warning("task_recovered", extra={"outcome": f"stale={count}"})
        return count

    async def run_once(self) -> dict[str, Any] | None:
        """Claim one task and drive it to a terminal status. None when idle."""
        task_id = self.tasks.claim_next()
        if task_id is None:
            return None
        params = self.tasks.params(task_id)
        payload: dict[str, Any]
        try:
            result = await self.analysis.run(
                cv_version_id=str(params["cv_version_id"]),
                snapshot_id=str(params["snapshot_id"]),
                force=bool(params.get("force", False)),
                progress=lambda step: self.tasks.set_step(task_id, step),
                should_stop=lambda: self.tasks.cancel_pending(task_id),
            )
        except PipelineCancelled:
            # The boundary sits before the next model call, so nothing was spent
            # after the request arrived.
            payload = self.tasks.mark_cancelled(task_id)
            logger.info("task_cancelled")
        except asyncio.CancelledError:
            # Shutdown, not failure: hand the task back so the next start resumes it.
            self.tasks.release(task_id)
            raise
        except AppError as exc:
            payload = self.tasks.fail(task_id, code=exc.code)
            logger.error("task_failed", extra={"outcome": exc.code})
        except Exception as exc:  # noqa: BLE001 - one bad task must not stop the worker
            payload = self.tasks.fail(task_id, code=type(exc).__name__)
            logger.error("task_failed", extra={"outcome": type(exc).__name__})
        else:
            payload = self.tasks.succeed(task_id, analysis_id=str(result["id"]))
            logger.info("task_ok")
        return payload

    async def run_forever(self, stop_event: asyncio.Event) -> None:
        self.recover()
        while not stop_event.is_set():
            payload = await self.run_once()
            if payload is not None:
                continue
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.poll_seconds)
            except TimeoutError:
                continue
