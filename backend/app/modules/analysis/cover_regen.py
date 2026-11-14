"""Re-running S7 and S8 from stored verdicts.

The draft is written again from the rows the analysis already has: no matching,
no suggestions, no extraction. The guard runs exactly as it does in the pipeline,
so a rejected attempt never replaces a note that already passed (E25).
"""

from __future__ import annotations

from typing import Any, NoReturn

from sqlalchemy.orm import Session, sessionmaker

from app.modules.analysis import call_ledger, queries
from app.modules.analysis.constraints import UserConstraints
from app.modules.analysis.cover import CoverNoteResult, CoverWriter
from app.modules.analysis.packet import BriefFor, load
from app.modules.analysis.payload import result_of, structure_of
from app.modules.analysis.schemas import JdStructure
from app.modules.analysis.scoring import RequirementResult
from app.modules.cvs.service import CvService
from app.modules.jobs.service import JobService
from app.shared.errors import AppError


def inputs(
    session: Session, analysis_id: str
) -> tuple[str, str, JdStructure | None, list[RequirementResult]]:
    """Everything S7 needs, read back from rows instead of from the pipeline."""
    analysis = queries.get_analysis(session, analysis_id)
    if analysis is None:
        raise AppError("NOT_FOUND", "That analysis does not exist.", {"analysis_id": analysis_id})
    extraction = queries.get_extraction(session, analysis.extraction_id)
    if extraction is None:
        raise AppError(
            "NOT_FOUND",
            "That analysis has no extraction to regenerate from.",
            {"analysis_id": analysis_id},
        )
    requirements = queries.list_requirements(session, analysis.extraction_id, active_only=False)
    matches = {match.requirement_id: match for match in queries.list_matches(session, analysis.id)}
    results = [
        result_of(requirement, matches.get(requirement.id))
        for requirement in requirements
        if requirement.active
    ]
    return (
        analysis.cv_version_id,
        extraction.jd_snapshot_id,
        structure_of(extraction),
        results,
    )


def _store(
    session_factory: sessionmaker[Session], analysis_id: str, cover: CoverNoteResult
) -> None:
    with session_factory() as session:
        analysis = queries.get_analysis(session, analysis_id)
        if analysis is None:
            raise AppError(
                "NOT_FOUND", "That analysis does not exist.", {"analysis_id": analysis_id}
            )
        analysis.cover_note = cover.note.text
        analysis.cover_note_guard = cover.note.status
        analysis.cover_note_reason = cover.note.reason
        analysis.cover_note_edited = None
        session.commit()


def _reject(cover: CoverNoteResult, analysis_id: str) -> NoReturn:
    raise AppError(
        "COVER_NOTE_REJECTED",
        "The new draft failed verification twice, so the existing note is unchanged.",
        {
            "analysis_id": analysis_id,
            "guard_status": cover.note.status,
            "guard_reason": cover.note.reason,
        },
    )


async def regenerate(
    session_factory: sessionmaker[Session],
    *,
    cvs: CvService,
    jobs: JobService,
    cover_writer: CoverWriter,
    analysis_id: str,
    constraints: UserConstraints,
    brief_for: BriefFor,
) -> dict[str, Any]:
    """Run S7 and S8 again from stored verdicts. S2..S5 are not re-run."""
    with session_factory() as session:
        cv_version_id, snapshot_id, structure, results = inputs(session, analysis_id)
    cv = cvs.parser_view(cv_version_id)
    snapshot = jobs.snapshot(snapshot_id)
    # The analysis already exists here, so its calls can name it directly.
    with call_ledger.ledger(analysis_id=analysis_id):
        cover = await cover_writer.write(
            structure=structure,
            results=results,
            cv_text=cv["text"],
            jd_text=snapshot["raw_text"],
            section_texts=cv.get("section_texts"),
        )
    if not cover.note.visible:
        _reject(cover, analysis_id)
    _store(session_factory, analysis_id, cover)
    with session_factory() as session:
        return load(session, analysis_id, constraints=constraints, brief_for=brief_for)
