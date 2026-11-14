"""S0..S9 for one CV version against one JD snapshot.

The steps in order, the cache check before they run, and the write at the end.
The order lives here and nowhere else: S1 then S2 (which grounds and votes) then
S5 then S7, with a cancel checked at every boundary so a cancel never begins
another model call.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from sqlalchemy.orm import Session, sessionmaker

from app.modules.analysis import call_ledger, keys, packet, writer
from app.modules.analysis.constraints import UserConstraints
from app.modules.analysis.cover import CoverWriter
from app.modules.analysis.enums import Step
from app.modules.analysis.matcher import Matcher
from app.modules.analysis.prompts import load_prompt
from app.modules.analysis.structurer import JdStructurer
from app.modules.analysis.suggest import Suggester
from app.modules.analysis.writer import Draft
from app.modules.cvs.service import CvService
from app.modules.jobs.service import JobService
from app.shared.clock import Clock

MATCH_PROMPT: Final = "match"


class PipelineCancelled(Exception):
    """The task was cancelled; the pipeline stopped at a step boundary."""


def _ignore_step(_step: str) -> None:
    return None


def _never_stop() -> bool:
    return False


def raise_if_cancelled(stop: Callable[[], bool]) -> None:
    if stop():
        raise PipelineCancelled


@dataclass(frozen=True, slots=True)
class Pipeline:
    """The steps and everything they are allowed to touch."""

    session_factory: sessionmaker[Session]
    cvs: CvService
    jobs: JobService
    structurer: JdStructurer
    matcher: Matcher
    suggester: Suggester
    cover_writer: CoverWriter
    prompts_dir: Path
    model: str
    clock: Clock
    constraints: Callable[[], UserConstraints]

    async def run(
        self,
        *,
        cv_version_id: str,
        snapshot_id: str,
        force: bool = False,
        progress: Callable[[str], None] | None = None,
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        """S1..S9, with every model call attributed to the analysis it pays for.

        `progress` receives the step that is about to start, so a queued task can
        report where it is. Steps that complete inside a single call (S3/S4 inside
        match, S6 inside suggest, S8 inside cover) are reported at that call's
        boundary; only S0..S9 are observable from here.
        """
        with call_ledger.ledger() as calls:
            return await self._execute(
                cv_version_id=cv_version_id,
                snapshot_id=snapshot_id,
                force=force,
                progress=progress,
                should_stop=should_stop,
                calls=calls,
            )

    async def _execute(
        self,
        *,
        cv_version_id: str,
        snapshot_id: str,
        force: bool,
        progress: Callable[[str], None] | None,
        should_stop: Callable[[], bool] | None,
        calls: call_ledger.CallLedger,
    ) -> dict[str, Any]:
        on_step = progress or _ignore_step
        stop = should_stop or _never_stop
        raise_if_cancelled(stop)
        cv = self.cvs.parser_view(cv_version_id)
        snapshot = self.jobs.snapshot(snapshot_id)
        bundle = self.match_bundle()
        key = self.cache_key_for(cv=cv, snapshot=snapshot, match_bundle=bundle)
        if not force:
            cached_id = self.cached_id(key)
            if cached_id is not None:
                return {**self.load(cached_id), "cache_hit": True}

        draft = await self.produce(cv=cv, snapshot=snapshot, on_step=on_step, stop=stop)

        on_step(Step.S9_PERSIST)
        analysis_id = writer.persist(
            self.session_factory,
            draft,
            cv_version_id=cv_version_id,
            key=key,
            bundle=bundle,
            model=self.model,
            runs=self.matcher.runs,
            clock=self.clock,
            replace=force,
            call_ids=calls.pending,
        )
        # F06: the job now has an analysis, so its status moves off "new".
        self.jobs.mark_analyzed(snapshot["job_id"])
        return {**self.load(analysis_id), "cache_hit": False}

    async def produce(
        self,
        *,
        cv: dict[str, Any],
        snapshot: dict[str, Any],
        on_step: Callable[[str], None],
        stop: Callable[[], bool],
    ) -> Draft:
        """S1, S2, S5, S7 in order, each announced before it starts."""
        on_step(Step.S1_EXTRACT)
        raise_if_cancelled(stop)
        structured = await self.structurer.run(
            snapshot_id=snapshot["id"],
            raw_text=snapshot["raw_text"],
            text_sha256=snapshot["text_sha256"],
        )

        on_step(Step.S2_MATCH)
        raise_if_cancelled(stop)
        matched = await self.matcher.match(requirements=structured.requirements, cv_text=cv["text"])

        on_step(Step.S5_SUGGEST)
        raise_if_cancelled(stop)
        suggested = await self.suggester.suggest(
            results=matched.results,
            cv_text=cv["text"],
            section_texts=cv.get("section_texts"),
        )

        on_step(Step.S7_COVER_NOTE)
        raise_if_cancelled(stop)
        cover = await self.cover_writer.write(
            structure=structured.structure,
            results=matched.results,
            cv_text=cv["text"],
            jd_text=snapshot["raw_text"],
            section_texts=cv.get("section_texts"),
        )
        return Draft(structured=structured, matched=matched, suggested=suggested, cover=cover)

    def probe(self, *, cv_version_id: str, snapshot_id: str) -> dict[str, Any]:
        """The cache key for this pair, plus the stored analysis when one exists.

        No model call and no extraction row: the key is derived from the stored
        snapshot, so the queue can answer before spending a token.
        """
        cv = self.cvs.parser_view(cv_version_id)
        snapshot = self.jobs.snapshot(snapshot_id)
        key = self.cache_key_for(cv=cv, snapshot=snapshot, match_bundle=self.match_bundle())
        return {
            "cache_key": key,
            "analysis_id": self.cached_id(key),
            "cv_version_id": cv_version_id,
            "snapshot_id": snapshot_id,
        }

    def match_bundle(self) -> str:
        """The prompt set the packets are written with; part of the cache key."""
        return load_prompt(self.prompts_dir, MATCH_PROMPT).ref.bundle

    def cache_key_for(
        self,
        *,
        cv: dict[str, Any],
        snapshot: dict[str, Any],
        match_bundle: str,
        params: dict[str, Any] | None = None,
    ) -> str:
        return keys.analysis_key(
            cv=cv,
            snapshot=snapshot,
            match_bundle=match_bundle,
            model=self.model,
            runs=self.matcher.runs,
            cover_writer=self.cover_writer,
            params=params,
        )

    def load(self, analysis_id: str, *, include_rejected: bool = False) -> dict[str, Any]:
        with self.session_factory() as session:
            return packet.load(
                session,
                analysis_id,
                constraints=self.constraints(),
                brief_for=self.jobs.job_brief_for_snapshot,
                include_rejected=include_rejected,
            )

    def cached_id(self, key: str) -> str | None:
        return packet.analysis_id_for_key(self.session_factory, key)
