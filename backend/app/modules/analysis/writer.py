"""S9: write one packet, or rewrite the one that already owns the cache key.

This is the only place in the analysis module that writes a packet. It is kept
apart from the step orchestration because the write has rules the steps do not:
one analysis per cache key, a forced re-run reuses that row, and the LLM calls
the run already paid for are linked here because the row did not exist when they
were recorded.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from app.modules.analysis import call_ledger, packet, queries
from app.modules.analysis.cover import CoverNoteResult
from app.modules.analysis.enums import AnalysisStatus
from app.modules.analysis.matcher import MatchResult
from app.modules.analysis.models import Analysis
from app.modules.analysis.suggest import SuggestionResult, rows_for
from app.modules.analysis.views import StructuredJd
from app.shared.clock import Clock


@dataclass(frozen=True, slots=True)
class Draft:
    """What S1..S7 returned, held together until S9 can write it."""

    structured: StructuredJd
    matched: MatchResult
    suggested: SuggestionResult
    cover: CoverNoteResult


def persist(
    session_factory: sessionmaker[Session],
    draft: Draft,
    *,
    cv_version_id: str,
    key: str,
    bundle: str,
    model: str,
    runs: int,
    clock: Clock,
    replace: bool = False,
    call_ids: list[str] | None = None,
) -> str:
    """Store the packet and return its id."""
    unstable = sum(1 for item in draft.matched.results if "unstable" in item.flags)
    with session_factory() as session:
        analysis = _row(
            session,
            cv_version_id=cv_version_id,
            extraction_id=draft.structured.extraction_id,
            key=key,
            bundle=bundle,
            cover=draft.cover,
            replace=replace,
            stability={"unstable_count": unstable},
            model=model,
            runs=runs,
            clock=clock,
        )
        session.flush()
        session.add_all(packet.match_rows(analysis.id, draft.matched.results))
        session.add_all(rows_for(analysis.id, draft.suggested))
        session.flush()
        call_ledger.attach(session, list(call_ids or ()), analysis_id=analysis.id)
        session.commit()
        return analysis.id


def _row(
    session: Session,
    *,
    cv_version_id: str,
    extraction_id: str,
    key: str,
    bundle: str,
    cover: CoverNoteResult,
    replace: bool,
    stability: dict[str, int],
    model: str,
    runs: int,
    clock: Clock,
) -> Analysis:
    """The analysis row that owns `key`, created here or reused on force."""
    analysis = _open_row(
        session, cv_version_id=cv_version_id, extraction_id=extraction_id, key=key,
        clock=clock, replace=replace,
    )
    analysis.model = model
    analysis.prompt_bundle = bundle
    analysis.match_runs = runs
    analysis.status = AnalysisStatus.OK
    analysis.stability = stability
    analysis.cover_note = cover.note.text
    analysis.cover_note_edited = None
    analysis.cover_note_guard = cover.note.status
    analysis.cover_note_reason = cover.note.reason
    return analysis


def _open_row(
    session: Session,
    *,
    cv_version_id: str,
    extraction_id: str,
    key: str,
    clock: Clock,
    replace: bool,
) -> Analysis:
    """Reuse the row for `key` with its children dropped, or make a fresh one."""
    analysis = queries.get_analysis_by_key(session, key) if replace else None
    if analysis is None:
        analysis = Analysis(
            cv_version_id=cv_version_id,
            extraction_id=extraction_id,
            cache_key=key,
            created_at=clock.now(),
        )
        session.add(analysis)
        return analysis
    for match in queries.list_matches(session, analysis.id):
        session.delete(match)
    for row in queries.list_suggestions(session, analysis.id):
        session.delete(row)
    session.flush()
    analysis.cv_version_id = cv_version_id
    analysis.extraction_id = extraction_id
    return analysis
