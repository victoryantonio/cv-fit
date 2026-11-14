"""The analysis service: one face for the API, the worker and the queue.

The steps and the write live in `pipeline` and `writer`; reading and changing a
stored packet lives in `packet`; re-running the cover note lives in
`cover_regen`. This module is only the seam to the callers, so nothing outside
has to know which of those it is talking to.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.modules.analysis import cover_regen, packet
from app.modules.analysis.keys import cache_key
from app.modules.analysis.pipeline import Pipeline, PipelineCancelled

__all__ = ["AnalysisService", "PipelineCancelled", "cache_key"]


@dataclass(frozen=True, slots=True)
class AnalysisService:
    """One CV version against one JD snapshot, from queue to packet."""

    pipeline: Pipeline

    async def run(
        self,
        *,
        cv_version_id: str,
        snapshot_id: str,
        force: bool = False,
        progress: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        return await self.pipeline.run(
            cv_version_id=cv_version_id,
            snapshot_id=snapshot_id,
            force=force,
            progress=progress,
            should_stop=should_stop,
        )

    def probe(self, *, cv_version_id: str, snapshot_id: str) -> dict[str, Any]:
        return self.pipeline.probe(cv_version_id=cv_version_id, snapshot_id=snapshot_id)

    def get(self, analysis_id: str, *, include_rejected: bool = False) -> dict[str, Any]:
        return self.pipeline.load(analysis_id, include_rejected=include_rejected)

    def set_suggestion_decision(
        self, suggestion_id: str, *, decision: str, reason: str | None = None
    ) -> dict[str, Any]:
        return packet.decide_suggestion(
            self.pipeline.session_factory, suggestion_id, decision=decision, reason=reason
        )

    def set_requirement_active(self, requirement_id: str, *, active: bool) -> dict[str, Any]:
        return packet.set_requirement_active(
            self.pipeline.session_factory,
            requirement_id,
            active=active,
            constraints=self.pipeline.constraints(),
            brief_for=self.pipeline.jobs.job_brief_for_snapshot,
        )

    def history(self, job_id: str) -> dict[str, Any]:
        return packet.history(
            self.pipeline.session_factory,
            self.pipeline.jobs,
            job_id,
            constraints=self.pipeline.constraints(),
            brief_for=self.pipeline.jobs.job_brief_for_snapshot,
        )

    def set_cover_note_edited(self, analysis_id: str, *, text: str) -> dict[str, Any]:
        return packet.set_cover_note_edited(
            self.pipeline.session_factory,
            analysis_id,
            text=text,
            constraints=self.pipeline.constraints(),
            brief_for=self.pipeline.jobs.job_brief_for_snapshot,
        )

    async def regenerate_cover_note(self, analysis_id: str) -> dict[str, Any]:
        return await cover_regen.regenerate(
            self.pipeline.session_factory,
            cvs=self.pipeline.cvs,
            jobs=self.pipeline.jobs,
            cover_writer=self.pipeline.cover_writer,
            analysis_id=analysis_id,
            constraints=self.pipeline.constraints(),
            brief_for=self.pipeline.jobs.job_brief_for_snapshot,
        )
