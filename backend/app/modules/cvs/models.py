from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, new_id, utc_now


class CV(Base):
    __tablename__ = "cv"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    target_role: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class CVVersion(Base):
    __tablename__ = "cv_version"
    __table_args__ = (
        UniqueConstraint("cv_id", "version_no", name="uq_cv_version_no"),
        UniqueConstraint("cv_id", "file_sha256", name="uq_cv_version_file"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    cv_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("cv.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str | None] = mapped_column(String(200))
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    text_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    redacted_text: Mapped[str] = mapped_column(Text, nullable=False)
    structured: Mapped[Any | None] = mapped_column(JSON)
    parser_report: Mapped[Any | None] = mapped_column(JSON)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
