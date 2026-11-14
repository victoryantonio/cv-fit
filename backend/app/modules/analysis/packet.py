"""Reads and changes on one stored packet.

Everything here works from rows: the score, the label and the summary are
rebuilt on every read, so deactivating a requirement or changing a weight never
leaves a stale number behind.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from sqlalchemy.orm import Session, sessionmaker

from app.modules.analysis import queries
from app.modules.analysis.constraints import UserConstraints
from app.modules.analysis.enums import GuardStatus, SuggestionDecision
from app.modules.analysis.models import RequirementMatch
from app.modules.analysis.payload import build_payload
from app.modules.analysis.scoring import RequirementResult
from app.modules.analysis.suggest import as_payload, provenance
from app.modules.jobs.service import JobService
from app.shared.errors import AppError

SUMMARY_KEYS: Final[tuple[str, ...]] = ("label", "coverage", "counts", "must_have")

BriefFor = Callable[[str], dict[str, Any] | None]


def load(
    session: Session,
    analysis_id: str,
    *,
    constraints: UserConstraints,
    brief_for: BriefFor,
    include_rejected: bool = False,
) -> dict[str, Any]:
    return build_payload(
        session,
        analysis_id,
        constraints=constraints,
        brief_for=brief_for,
        include_rejected=include_rejected,
    )


def analysis_id_for_key(
    session_factory: sessionmaker[Session], key: str
) -> str | None:
    """The analysis that already owns this cache key, if any."""
    with session_factory() as session:
        analysis = queries.get_analysis_by_key(session, key)
        return analysis.id if analysis is not None else None


def match_rows(analysis_id: str, results: list[RequirementResult]) -> list[RequirementMatch]:
    return [
        RequirementMatch(
            analysis_id=analysis_id,
            requirement_id=item.requirement_id,
            verdict=item.verdict,
            evidence_quote=item.evidence_quote,
            rationale=item.rationale,
            votes=dict(item.votes),
            agreement=item.agreement,
            flags=list(item.flags),
        )
        for item in results
    ]


def _check_decision(decision: str) -> None:
    allowed = {item.value for item in SuggestionDecision}
    if decision not in allowed:
        raise AppError(
            "INVALID_DECISION",
            "That is not a decision this tool records.",
            {"decision": decision, "allowed": sorted(allowed)},
        )


def _require_suggestion(session: Session, suggestion_id: str) -> Any:
    suggestion = queries.get_suggestion(session, suggestion_id)
    if suggestion is None:
        raise AppError(
            "NOT_FOUND",
            "That suggestion does not exist.",
            {"suggestion_id": suggestion_id},
        )
    return suggestion


def _check_acceptable(suggestion: Any, decision: str) -> None:
    """A suggestion the fabrication guard rejected can never be accepted."""
    if decision == SuggestionDecision.ACCEPTED and suggestion.guard_status != GuardStatus.PASS:
        raise AppError(
            "GUARD_BLOCKED",
            "The fabrication guard rejected this suggestion, so it cannot be accepted.",
            {"suggestion_id": suggestion.id, "guard_status": suggestion.guard_status},
        )


def decide_suggestion(
    session_factory: sessionmaker[Session],
    suggestion_id: str,
    *,
    decision: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Accept or reject one suggestion. A blocked one can never be accepted."""
    _check_decision(decision)
    with session_factory() as session:
        suggestion = _require_suggestion(session, suggestion_id)
        _check_acceptable(suggestion, decision)
        suggestion.decision = decision
        suggestion.decision_reason = reason
        session.commit()
        payload = as_payload(suggestion)
        counts = provenance(queries.list_suggestions(session, suggestion.analysis_id))
    return {"suggestion": payload, "suggestion_provenance": counts}


def set_requirement_active(
    session_factory: sessionmaker[Session],
    requirement_id: str,
    *,
    active: bool,
    constraints: UserConstraints,
    brief_for: BriefFor,
) -> dict[str, Any]:
    """Flip one requirement and return every affected analysis, recomputed."""
    with session_factory() as session:
        requirement = queries.get_requirement(session, requirement_id)
        if requirement is None:
            raise AppError(
                "NOT_FOUND",
                "That requirement does not exist.",
                {"requirement_id": requirement_id},
            )
        requirement.active = active
        session.commit()
        return {
            "requirement": {
                "id": requirement.id,
                "position": requirement.position,
                "text": requirement.text,
                "importance": requirement.importance,
                "active": requirement.active,
            },
            "analyses": [
                load(session, analysis_id, constraints=constraints, brief_for=brief_for)
                for analysis_id in queries.analyses_for_requirement(session, requirement_id)
            ],
        }


def _history_item(analysis: Any, payload: dict[str, Any], newest: Any) -> dict[str, Any]:
    return {
        "analysis_id": analysis.id,
        "cv_version_id": analysis.cv_version_id,
        "created_at": analysis.created_at,
        "model": analysis.model,
        "prompt_bundle": analysis.prompt_bundle,
        "summary": {key: payload["summary"][key] for key in SUMMARY_KEYS},
        # A different model or prompt set makes the numbers incomparable, so the
        # UI has to be able to flag it.
        "comparable": (
            analysis.model == newest.model and analysis.prompt_bundle == newest.prompt_bundle
        ),
    }


def history(
    session_factory: sessionmaker[Session],
    jobs: JobService,
    job_id: str,
    *,
    constraints: UserConstraints,
    brief_for: BriefFor,
) -> dict[str, Any]:
    """Analyses for one job, newest first, with comparability against the newest."""
    snapshot_ids = jobs.snapshot_ids(job_id)
    with session_factory() as session:
        rows = queries.analyses_for_snapshots(session, snapshot_ids)
        if not rows:
            return {"job_id": job_id, "items": []}
        newest = rows[0]
        items = [
            _history_item(
                analysis,
                load(session, analysis.id, constraints=constraints, brief_for=brief_for),
                newest,
            )
            for analysis in rows
        ]
    return {"job_id": job_id, "items": items}


def set_cover_note_edited(
    session_factory: sessionmaker[Session],
    analysis_id: str,
    *,
    text: str,
    constraints: UserConstraints,
    brief_for: BriefFor,
) -> dict[str, Any]:
    """Store your own wording. The guard checked the draft, not your edit."""
    with session_factory() as session:
        analysis = queries.get_analysis(session, analysis_id)
        if analysis is None:
            raise AppError(
                "NOT_FOUND", "That analysis does not exist.", {"analysis_id": analysis_id}
            )
        analysis.cover_note_edited = text
        session.commit()
        return load(session, analysis_id, constraints=constraints, brief_for=brief_for)

