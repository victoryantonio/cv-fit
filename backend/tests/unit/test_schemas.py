"""The output contract: credit needs a quote, extra fields are refused."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.modules.analysis.enums import Importance, Verdict
from app.modules.analysis.schemas import (
    CoverNoteDraft,
    JdStructure,
    MatchVerdict,
    SuggestionBatch,
    load_payload,
)


def test_strong_verdict_without_a_quote_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MatchVerdict(verdict=Verdict.STRONG, rationale="looks fine")


def test_partial_verdict_without_a_quote_is_rejected() -> None:
    with pytest.raises(ValidationError):
        MatchVerdict(verdict=Verdict.PARTIAL, evidence_quote="   ")


def test_gap_verdict_must_not_carry_a_quote() -> None:
    with pytest.raises(ValidationError):
        MatchVerdict(verdict=Verdict.GAP, evidence_quote="some CV line")


def test_strong_verdict_with_a_quote_passes() -> None:
    verdict = MatchVerdict(
        verdict=Verdict.STRONG,
        evidence_quote="Led the migration of the settlement service",
        rationale="Matches the requirement as written.",
    )
    assert verdict.verdict is Verdict.STRONG


def test_unknown_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        MatchVerdict(verdict=Verdict.GAP, score=0.8)


def test_job_post_without_requirements_is_rejected() -> None:
    with pytest.raises(ValidationError):
        JdStructure(is_job_post=True, title="Backend Engineer")


def test_non_job_post_needs_no_requirements() -> None:
    structure = JdStructure(is_job_post=False, job_count=0)
    assert structure.requirements == []


def test_importance_counts_toward_weighting() -> None:
    structure = load_payload(
        "jd_structure",
        {
            "is_job_post": True,
            "job_count": 1,
            "title": "Backend Engineer",
            "requirements": [
                {
                    "text": "5+ years of backend experience",
                    "category": "experience",
                    "importance": "knockout",
                    "keywords": ["backend"],
                    "jd_quote": "5+ years of professional backend engineering experience.",
                }
            ],
        },
    )
    assert isinstance(structure, JdStructure)
    assert structure.requirements[0].importance is Importance.KNOCKOUT


def test_suggestion_batch_limit_is_enforced() -> None:
    with pytest.raises(ValidationError):
        SuggestionBatch(
            suggestions=[
                {"proposed_text": f"line {index}", "rationale": "r"} for index in range(13)
            ]
        )


def test_cover_note_requires_a_real_body() -> None:
    with pytest.raises(ValidationError):
        CoverNoteDraft(text="short")


def test_unknown_schema_name_is_a_key_error() -> None:
    with pytest.raises(KeyError):
        load_payload("no_such_schema", {})
