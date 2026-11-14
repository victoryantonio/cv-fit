"""Tables for extraction, analysis, suggestions and the task queue.

Scores and the fit label are deliberately absent: they are derived at read time
so a settings change cannot leave a stale number in the database.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, new_id, utc_now
from app.modules.analysis.enums import (
    AnalysisStatus,
    ExtractionStatus,
    GuardStatus,
    Importance,
    LlmOutcome,
    RequirementCategory,
    SuggestionDecision,
    SuggestionScope,
    SuggestionTarget,
    SuggestionType,
    TaskKind,
    TaskStatus,
    Verdict,
)


class JdExtraction(Base):
    """Keyed by extract_key: one job post, one requirement set."""

    __tablename__ = "jd_extraction"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    jd_snapshot_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jd_snapshot.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    extract_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_bundle: Mapped[str] = mapped_column(String(64), nullable=False)
    structured: Mapped[Any | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=ExtractionStatus.OK)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class JdRequirement(Base):
    __tablename__ = "jd_requirement"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    extraction_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("jd_extraction.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(
        String(20), nullable=False, default=RequirementCategory.OTHER
    )
    importance: Mapped[str] = mapped_column(String(20), nullable=False, default=Importance.NICE)
    keywords: Mapped[Any | None] = mapped_column(JSON)
    jd_quote: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class Analysis(Base):
    __tablename__ = "analysis"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cv_version_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("cv_version.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    extraction_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jd_extraction.id"), nullable=False, index=True
    )
    cache_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_bundle: Mapped[str] = mapped_column(String(64), nullable=False)
    match_runs: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AnalysisStatus.QUEUED, index=True
    )
    stability: Mapped[Any | None] = mapped_column(JSON)
    cover_note: Mapped[str | None] = mapped_column(Text)
    cover_note_edited: Mapped[str | None] = mapped_column(Text)
    cover_note_guard: Mapped[str | None] = mapped_column(String(40))
    cover_note_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class RequirementMatch(Base):
    __tablename__ = "requirement_match"
    __table_args__ = (UniqueConstraint("analysis_id", "requirement_id", name="uq_match_pair"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("jd_requirement.id"), nullable=False, index=True
    )
    verdict: Mapped[str] = mapped_column(String(10), nullable=False, default=Verdict.GAP)
    evidence_quote: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    votes: Mapped[Any | None] = mapped_column(JSON)
    agreement: Mapped[float | None] = mapped_column(Float)
    flags: Mapped[Any | None] = mapped_column(JSON)


class Suggestion(Base):
    __tablename__ = "suggestion"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("analysis.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jd_requirement.id"))
    type: Mapped[str] = mapped_column(String(20), nullable=False, default=SuggestionType.REWORD)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default=SuggestionScope.GENERAL)
    target_section: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SuggestionTarget.OTHER
    )
    original_text: Mapped[str | None] = mapped_column(Text)
    proposed_text: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)
    guard_status: Mapped[str] = mapped_column(String(40), nullable=False, default=GuardStatus.PASS)
    guard_reason: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str] = mapped_column(
        String(20), nullable=False, default=SuggestionDecision.UNDECIDED
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)


class AnalysisTask(Base):
    __tablename__ = "analysis_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default=TaskKind.ANALYZE)
    params: Mapped[Any | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TaskStatus.QUEUED, index=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(60))
    current_step: Mapped[str | None] = mapped_column(String(30))
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    analysis_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("analysis.id", ondelete="SET NULL")
    )


class LlmCall(Base):
    """Metadata only. Prompt text and content are never written here."""

    __tablename__ = "llm_call"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    analysis_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("analysis.id", ondelete="CASCADE"), index=True
    )
    step: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    tokens_in: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cache_hit: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default=LlmOutcome.OK)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
