"""Request and response bodies for the analysis endpoints.

Kept apart from the routes so the shapes can be read in one place and the
router file stays about wiring.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AnalysisCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cv_version_id: str = Field(min_length=1)
    snapshot_id: str = Field(min_length=1)
    force: bool = False
    override_budget: bool = False


class TaskOut(BaseModel):
    id: str
    kind: str
    status: str
    current_step: str | None = None
    attempts: int
    error_code: str | None = None
    analysis_id: str | None = None
    cache_key: str | None = None
    cancel_requested: bool
    created_at: datetime
    updated_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class AnalysisQueuedOut(BaseModel):
    """The 202 body: a task id to poll, never a partial packet."""

    task: TaskOut
    cache_key: str


class RequirementPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool


class SuggestionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str = Field(min_length=1)
    reason: str | None = Field(default=None, max_length=400)


class RequirementOut(BaseModel):
    id: str
    position: int
    text: str
    importance: str
    active: bool


class MatchOut(BaseModel):
    requirement_id: str
    verdict: str
    evidence_quote: str | None = None
    rationale: str | None = None
    votes: dict[str, int]
    agreement: float
    flags: list[str]


class ItemOut(BaseModel):
    requirement_id: str
    text: str
    evidence_quote: str | None = None
    verdict: str | None = None


class MustHaveOut(BaseModel):
    met: int
    total: int
    coverage: float


class ConstraintFlagOut(BaseModel):
    kind: str
    status: str
    note: str
    jd_value: str | None = None
    user_value: str | None = None


class SummaryOut(BaseModel):
    label: str
    coverage: int
    counts: dict[str, int]
    must_have: MustHaveOut
    knockout_gaps: list[ItemOut]
    strongest: list[ItemOut]
    biggest_gaps: list[ItemOut]
    unstable_count: int
    constraint_flags: list[ConstraintFlagOut]


class JobBriefOut(BaseModel):
    title: str | None = None
    company: str | None = None


class SuggestionOut(BaseModel):
    id: str
    requirement_id: str | None = None
    type: str
    scope: str
    target_section: str
    original_text: str | None = None
    proposed_text: str | None = None
    rationale: str | None = None
    guard_status: str
    guard_reason: str | None = None
    decision: str
    decision_reason: str | None = None


class ProvenanceOut(BaseModel):
    total: int
    visible: int
    hidden: int
    rejected_by_rule: dict[str, int]


class CoverNoteOut(BaseModel):
    text: str | None = None
    generated: str | None = None
    edited: str | None = None
    guard_status: str | None = None
    guard_reason: str | None = None
    is_draft: bool = True
    word_count: int = 0


class SuggestionPatchOut(BaseModel):
    suggestion: SuggestionOut
    suggestion_provenance: ProvenanceOut


class CoverNotePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=4000)


class AnalysisOut(BaseModel):
    id: str
    status: str
    model: str
    prompt_bundle: str
    match_runs: int
    cache_key: str | None = None
    created_at: datetime
    cv_version_id: str
    extraction_id: str
    snapshot_id: str | None = None
    job_id: str | None = None
    job: JobBriefOut
    requirements: list[RequirementOut]
    matches: list[MatchOut]
    summary: SummaryOut
    suggestions: list[SuggestionOut]
    suggestion_provenance: ProvenanceOut
    suggestions_rejected: list[SuggestionOut] = []
    cover_note: CoverNoteOut | None = None


class AnalysisRunOut(AnalysisOut):
    cache_hit: bool


class RequirementPatchOut(BaseModel):
    requirement: RequirementOut
    analyses: list[AnalysisOut]


class HistorySummaryOut(BaseModel):
    label: str
    coverage: int
    counts: dict[str, int]
    must_have: MustHaveOut


class HistoryItemOut(BaseModel):
    analysis_id: str
    cv_version_id: str
    created_at: datetime
    model: str
    prompt_bundle: str
    summary: HistorySummaryOut
    comparable: bool


class HistoryOut(BaseModel):
    job_id: str
    items: list[HistoryItemOut]


