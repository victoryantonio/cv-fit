"""Pydantic models for every LLM output.

These models are the contract between the prompt files and the pipeline: the
prompts describe the shape, the JSON Schema snapshot is committed, and any
drift fails a contract test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.analysis.enums import (
    Importance,
    RequirementCategory,
    SuggestionScope,
    SuggestionTarget,
    SuggestionType,
    Verdict,
)


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class JdRequirementOut(_Strict):
    text: str = Field(min_length=3, max_length=400)
    category: RequirementCategory = RequirementCategory.OTHER
    importance: Importance = Importance.NICE
    keywords: list[str] = Field(default_factory=list, max_length=12)
    jd_quote: str = Field(min_length=3)

    @model_validator(mode="after")
    def _quote_is_short(self) -> JdRequirementOut:
        if len(self.jd_quote) > 600:
            raise ValueError("jd_quote is longer than 600 characters")
        return self


class JdStructure(_Strict):
    """S1 output. `is_job_post` is what turns into JD_NOT_FOUND / JD_MULTIPLE_JOBS."""

    is_job_post: bool = True
    job_count: int = Field(default=1, ge=0, le=20)
    title: str | None = Field(default=None, max_length=200)
    company: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    work_mode: Literal["remote", "hybrid", "onsite", "unknown"] = "unknown"
    seniority: str | None = Field(default=None, max_length=80)
    languages: list[str] = Field(default_factory=list, max_length=10)
    salary_text: str | None = Field(default=None, max_length=300)
    work_authorization_text: str | None = Field(default=None, max_length=300)
    requirements: list[JdRequirementOut] = Field(default_factory=list, max_length=60)

    @model_validator(mode="after")
    def _job_post_needs_requirements(self) -> JdStructure:
        if self.is_job_post and not self.requirements:
            raise ValueError("a job post must yield at least one requirement")
        return self


class MatchVerdict(_Strict):
    """S2 output for one requirement. No quote means no credit."""

    verdict: Verdict = Verdict.GAP
    evidence_quote: str | None = Field(default=None, max_length=600)
    rationale: str = Field(default="", max_length=500)
    missing: list[str] = Field(default_factory=list, max_length=6)

    @model_validator(mode="after")
    def _credit_requires_evidence(self) -> MatchVerdict:
        quote = (self.evidence_quote or "").strip()
        if self.verdict is Verdict.GAP:
            if quote:
                raise ValueError("a gap verdict must not carry an evidence quote")
            return self
        if not quote:
            raise ValueError("strong and partial verdicts require an evidence quote")
        return self


class SuggestionOut(_Strict):
    requirement_index: int | None = Field(default=None, ge=0)
    type: SuggestionType = SuggestionType.REWORD
    scope: SuggestionScope = SuggestionScope.GENERAL
    target_section: SuggestionTarget = SuggestionTarget.OTHER
    original_text: str | None = Field(default=None, max_length=1200)
    proposed_text: str | None = Field(default=None, max_length=1200)
    rationale: str = Field(default="", max_length=400)

    @model_validator(mode="after")
    def _gap_note_has_no_rewrite(self) -> SuggestionOut:
        body = (self.proposed_text or "").strip()
        if self.type is SuggestionType.GAP_NOTE:
            if body:
                raise ValueError("a gap_note must not carry rewrite text")
            return self
        if not body:
            raise ValueError("every suggestion except gap_note requires proposed_text")
        return self


class SuggestionBatch(_Strict):
    suggestions: list[SuggestionOut] = Field(default_factory=list, max_length=12)


class CoverNoteDraft(_Strict):
    """S7 output. `asserted_requirement_indexes` is what the guard checks."""

    text: str = Field(min_length=40, max_length=2000)
    asserted_requirement_indexes: list[int] = Field(default_factory=list, max_length=20)


SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "jd_structure": JdStructure,
    "match_verdict": MatchVerdict,
    "suggestion_batch": SuggestionBatch,
    "cover_note": CoverNoteDraft,
}

SCHEMA_DIR_NAME = "schemas"


def snapshot_dir(prompts_dir: Path) -> Path:
    return prompts_dir / SCHEMA_DIR_NAME


def render_schema(name: str) -> str:
    """Deterministic JSON Schema text: sorted keys, one trailing newline."""
    model = SCHEMA_MODELS[name]
    payload: dict[str, Any] = model.model_json_schema(mode="serialization")
    return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_schema_snapshots(prompts_dir: Path) -> list[Path]:
    target = snapshot_dir(prompts_dir)
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in SCHEMA_MODELS:
        path = target / f"{name}.json"
        path.write_text(render_schema(name), encoding="utf-8")
        written.append(path)
    return written


def load_payload(name: str, payload: dict[str, Any]) -> BaseModel:
    """Validate a raw payload against the named model. Raises pydantic ValidationError."""
    return SCHEMA_MODELS[name].model_validate(payload)
