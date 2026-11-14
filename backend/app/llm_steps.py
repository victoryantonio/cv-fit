"""The four LLM steps, built from config.

Which model, which prompt directory, how many votes per requirement and how many
requirements at once all come from settings; the steps themselves know none of
it. Kept apart from the composition root so the wiring there stays readable.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.modules.analysis.cover import CoverWriter
from app.modules.analysis.matcher import Matcher
from app.modules.analysis.ports import LLMClient
from app.modules.analysis.structurer import JdStructurer
from app.modules.analysis.suggest import Suggester
from app.shared.clock import Clock

Steps = tuple[JdStructurer, Matcher, Suggester, CoverWriter]


def build_steps(
    settings: Settings,
    *,
    session_factory: sessionmaker[Session],
    clock: Clock,
    llm: LLMClient,
) -> Steps:
    structurer = JdStructurer(
        llm=llm,
        session_factory=session_factory,
        prompts_dir=settings.prompts_dir,
        model=settings.llm_model,
        clock=clock,
    )
    matcher = Matcher(
        llm=llm,
        session_factory=session_factory,
        prompts_dir=settings.prompts_dir,
        model=settings.llm_model,
        clock=clock,
        runs=settings.match_runs,
        max_concurrency=settings.llm_max_concurrency,
    )
    suggester = Suggester(
        llm=llm,
        session_factory=session_factory,
        prompts_dir=settings.prompts_dir,
        model=settings.llm_model,
    )
    cover_writer = CoverWriter(
        llm=llm,
        session_factory=session_factory,
        prompts_dir=settings.prompts_dir,
        model=settings.llm_model,
        min_words=settings.cover_note_min_words,
        max_words=settings.cover_note_max_words,
    )
    return structurer, matcher, suggester, cover_writer
