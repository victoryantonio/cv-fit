from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, new_id, utc_now
from app.modules.jobs.enums import JobOutcome, JobSource, JobStatus


class JobPosting(Base):
    __tablename__ = "job_posting"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default=JobSource.MANUAL)
    email_message_id: Mapped[str | None] = mapped_column(String(255), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    company: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str | None] = mapped_column(String(1000), index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=JobStatus.NEW, index=True
    )
    filter_reason: Mapped[str | None] = mapped_column(String(200))
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(String(20), nullable=False, default=JobOutcome.NONE)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class JdSnapshot(Base):
    """Immutable. Editing a pasted page creates a new row."""

    __tablename__ = "jd_snapshot"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("job_posting.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    injection_flags: Mapped[Any | None] = mapped_column(JSON)
    truncation_warning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class JobSyncState(Base):
    """One row per alert source: when a sync last completed (F03 postcondition).

    Kept apart from `job_posting` because a sync that adds nothing still counts
    as a sync, and the UI shows that time either way.
    """

    __tablename__ = "job_sync_state"

    source: Mapped[str] = mapped_column(String(20), primary_key=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
