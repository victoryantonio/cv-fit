"""The packet you read: stored rows in, one JSON-ready dict out.

Every derived number (score, fit label, summary) is rebuilt here on every read,
so a weight change or a deactivated requirement cannot leave a stale score in the
database. Nothing in this module talks to a model, and nothing here is stored.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy.orm import Session

from app.modules.analysis import queries
from app.modules.analysis.constraints import UserConstraints, build_flags
from app.modules.analysis.cover import word_count
from app.modules.analysis.enums import GuardStatus, Verdict
from app.modules.analysis.models import (
    Analysis,
    JdExtraction,
    JdRequirement,
    RequirementMatch,
    Suggestion,
)
from app.modules.analysis.schemas import JdStructure
from app.modules.analysis.scoring import RequirementResult, RequirementScore, score
from app.modules.analysis.suggest import as_payload, provenance, visible_payloads
from app.modules.analysis.summary import build_summary
from app.shared.errors import AppError

NO_MATCH_FLAG: Final = "no_match"

BriefLookup = Callable[[str], dict[str, Any] | None]


def result_of(requirement: JdRequirement, match: RequirementMatch | None) -> RequirementResult:
    """A requirement without a stored match is a gap: absent evidence is no credit."""
    return RequirementResult(
        requirement_id=requirement.id,
        position=requirement.position,
        text=requirement.text,
        importance=requirement.importance,
        verdict=match.verdict if match is not None else Verdict.GAP,
        evidence_quote=match.evidence_quote if match is not None else None,
        rationale=match.rationale if match is not None else None,
        keywords=tuple(requirement.keywords or ()),
        votes=dict(match.votes or {}) if match is not None else {},
        agreement=(match.agreement or 0.0) if match is not None else 0.0,
        flags=tuple(match.flags or ()) if match is not None else (NO_MATCH_FLAG,),
    )


def structure_of(extraction: Any) -> JdStructure | None:
    if extraction is None or not extraction.structured:
        return None
    return JdStructure.model_validate(extraction.structured)


def _job(structure: JdStructure | None) -> dict[str, Any]:
    if structure is None:
        return {"title": None, "company": None}
    return {"title": structure.title, "company": structure.company}


def _cover_payload(analysis: Analysis) -> dict[str, Any]:
    """The draft as read, plus the edit when there is one. Always flagged draft."""
    text = analysis.cover_note_edited or analysis.cover_note
    return {
        "text": text,
        "generated": analysis.cover_note,
        "edited": analysis.cover_note_edited,
        "guard_status": analysis.cover_note_guard,
        "guard_reason": analysis.cover_note_reason,
        "is_draft": True,
        "word_count": word_count(text),
    }


def _requirement_payload(requirement: JdRequirement) -> dict[str, Any]:
    return {
        "id": requirement.id,
        "position": requirement.position,
        "text": requirement.text,
        "importance": requirement.importance,
        "active": requirement.active,
    }


def _match_payload(item: RequirementResult) -> dict[str, Any]:
    return {
        "requirement_id": item.requirement_id,
        "verdict": item.verdict,
        "evidence_quote": item.evidence_quote,
        "rationale": item.rationale,
        "votes": dict(item.votes),
        "agreement": item.agreement,
        "flags": list(item.flags),
    }


def _job_view(structure: JdStructure | None, brief: dict[str, Any] | None) -> dict[str, Any]:
    """The extraction may name no title or company; the job row usually still does."""
    job = _job(structure)
    if brief is not None:
        job["title"] = job.get("title") or brief["title"]
        job["company"] = job.get("company") or brief["company"]
    return job


def build_payload(
    session: Session,
    analysis_id: str,
    *,
    constraints: UserConstraints,
    brief_for: BriefLookup,
    include_rejected: bool = False,
) -> dict[str, Any]:
    """Assemble the read model. `brief_for` maps a snapshot id to its job row."""
    facts = _facts(session, analysis_id, constraints=constraints, brief_for=brief_for)
    payload = _packet(facts)
    if include_rejected:
        payload["suggestions_rejected"] = [
            as_payload(row)
            for row in facts.suggestions
            if row.guard_status != GuardStatus.PASS
        ]
    return payload


@dataclass(frozen=True, slots=True)
class _Facts:
    """Everything the read model is derived from, read once."""

    analysis: Analysis
    extraction: JdExtraction | None
    requirements: list[JdRequirement]
    results: list[RequirementResult]
    scored: RequirementScore
    structure: JdStructure | None
    flags: list[dict[str, Any]]
    suggestions: list[Suggestion]
    brief: dict[str, Any] | None


def _facts(
    session: Session,
    analysis_id: str,
    *,
    constraints: UserConstraints,
    brief_for: BriefLookup,
) -> _Facts:
    analysis = queries.get_analysis(session, analysis_id)
    if analysis is None:
        raise AppError(
            "NOT_FOUND", "That analysis does not exist.", {"analysis_id": analysis_id}
        )
    extraction = queries.get_extraction(session, analysis.extraction_id)
    requirements = queries.list_requirements(session, analysis.extraction_id, active_only=False)
    matches = {match.requirement_id: match for match in queries.list_matches(session, analysis.id)}
    results = [
        result_of(requirement, matches.get(requirement.id))
        for requirement in requirements
        if requirement.active
    ]
    structure = structure_of(extraction)
    return _Facts(
        analysis=analysis,
        extraction=extraction,
        requirements=requirements,
        results=results,
        scored=score(results),
        structure=structure,
        flags=build_flags(constraints, structure) if structure is not None else [],
        suggestions=queries.list_suggestions(session, analysis.id),
        brief=brief_for(extraction.jd_snapshot_id) if extraction is not None else None,
    )


def _packet(facts: _Facts) -> dict[str, Any]:
    analysis, extraction = facts.analysis, facts.extraction
    return {
        "id": analysis.id,
        "status": analysis.status,
        "model": analysis.model,
        "prompt_bundle": analysis.prompt_bundle,
        "match_runs": analysis.match_runs,
        "cache_key": analysis.cache_key,
        "created_at": analysis.created_at,
        "cv_version_id": analysis.cv_version_id,
        "extraction_id": analysis.extraction_id,
        "snapshot_id": extraction.jd_snapshot_id if extraction is not None else None,
        "job_id": facts.brief["id"] if facts.brief is not None else None,
        "job": _job_view(facts.structure, facts.brief),
        "requirements": [_requirement_payload(row) for row in facts.requirements],
        "matches": [_match_payload(item) for item in facts.results],
        "summary": build_summary(facts.results, scored=facts.scored, constraint_flags=facts.flags),
        "suggestions": visible_payloads(facts.suggestions),
        "suggestion_provenance": provenance(facts.suggestions),
        "cover_note": _cover_payload(analysis),
    }
