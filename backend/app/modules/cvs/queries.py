"""Database access for the cvs module. No business rules here."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Final

import sqlalchemy as sa
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.modules.cvs.models import CV, CVVersion

ANALYSIS_TABLE: Final = "analysis"


@dataclass(frozen=True, slots=True)
class CvSummary:
    id: str
    label: str
    target_role: str | None
    created_at: datetime
    version_count: int
    latest_version_id: str | None


def get_cv(session: Session, cv_id: str) -> CV | None:
    return session.get(CV, cv_id)


def get_version(session: Session, version_id: str) -> CVVersion | None:
    return session.get(CVVersion, version_id)


def list_versions(session: Session, cv_id: str) -> list[CVVersion]:
    statement = select(CVVersion).where(CVVersion.cv_id == cv_id).order_by(CVVersion.version_no)
    return list(session.scalars(statement))


def list_cvs(session: Session) -> list[CvSummary]:
    # Two queries and a dict: the list is single-user and short, so a grouped
    # join would buy nothing but type noise.
    versions_by_cv: dict[str, list[CVVersion]] = {}
    for version in session.scalars(select(CVVersion).order_by(CVVersion.version_no)):
        versions_by_cv.setdefault(version.cv_id, []).append(version)

    summaries: list[CvSummary] = []
    for cv in session.scalars(select(CV).order_by(CV.created_at, CV.id)):
        versions = versions_by_cv.get(cv.id, [])
        summaries.append(
            CvSummary(
                id=cv.id,
                label=cv.label,
                target_role=cv.target_role,
                created_at=cv.created_at,
                version_count=len(versions),
                latest_version_id=versions[-1].id if versions else None,
            )
        )
    return summaries


def next_version_no(session: Session, cv_id: str) -> int:
    highest = session.scalar(select(func.max(CVVersion.version_no)).where(CVVersion.cv_id == cv_id))
    return int(highest or 0) + 1


def find_version_by_file_sha(session: Session, cv_id: str, file_sha256: str) -> CVVersion | None:
    statement = select(CVVersion).where(
        CVVersion.cv_id == cv_id, CVVersion.file_sha256 == file_sha256
    )
    return session.scalars(statement).first()


def count_analyses_for_versions(session: Session, version_ids: list[str]) -> int:
    """FR-05 impact preview (E18).

    Named here because the count is asked per CV, but the columns belong to the
    analysis module: if `analysis.cv_version_id` is ever renamed, update this too.
    """
    if not version_ids:
        return 0
    table = sa.table(ANALYSIS_TABLE, sa.column("id"), sa.column("cv_version_id"))
    statement = (
        select(func.count()).select_from(table).where(table.c.cv_version_id.in_(version_ids))
    )
    return int(session.scalar(statement) or 0)
