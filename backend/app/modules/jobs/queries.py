"""Read queries for jobs and JD snapshots."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.jobs.models import JdSnapshot, JobPosting, JobSyncState


def get_job(session: Session, job_id: str) -> JobPosting | None:
    return session.get(JobPosting, job_id)


def list_jobs(
    session: Session, *, status: str | None = None, filtered: bool | None = None
) -> list[JobPosting]:
    """`filtered` picks a side of the pre-filter; None returns both."""
    statement = select(JobPosting).order_by(JobPosting.created_at.desc())
    if status is not None:
        statement = statement.where(JobPosting.status == status)
    if filtered is True:
        statement = statement.where(JobPosting.filter_reason.is_not(None))
    elif filtered is False:
        statement = statement.where(JobPosting.filter_reason.is_(None))
    return list(session.scalars(statement))


def find_job_by_url(session: Session, url: str) -> JobPosting | None:
    """The posting's URL is its identity across alert emails."""
    statement = select(JobPosting).where(JobPosting.url == url).order_by(JobPosting.created_at)
    return session.scalars(statement).first()


def find_job_by_message_and_title(
    session: Session, message_id: str, title: str
) -> JobPosting | None:
    """Fallback for cards without a URL: the email plus the title is the identity.

    A message id alone cannot be the key, because one digest email carries many
    cards.
    """
    statement = select(JobPosting).where(
        JobPosting.email_message_id == message_id, JobPosting.title == title
    )
    return session.scalars(statement).first()


def get_snapshot(session: Session, snapshot_id: str) -> JdSnapshot | None:
    return session.get(JdSnapshot, snapshot_id)


def list_snapshots(session: Session, job_id: str) -> list[JdSnapshot]:
    statement = (
        select(JdSnapshot)
        .where(JdSnapshot.job_id == job_id)
        .order_by(JdSnapshot.captured_at.desc())
    )
    return list(session.scalars(statement))


def snapshots_by_job(session: Session, job_ids: list[str]) -> dict[str, list[JdSnapshot]]:
    """One query for a whole page of jobs, then group in Python."""
    grouped: dict[str, list[JdSnapshot]] = {job_id: [] for job_id in job_ids}
    if not job_ids:
        return grouped
    statement = (
        select(JdSnapshot)
        .where(JdSnapshot.job_id.in_(job_ids))
        .order_by(JdSnapshot.captured_at.desc())
    )
    for snapshot in session.scalars(statement):
        grouped[snapshot.job_id].append(snapshot)
    return grouped


def find_snapshot(session: Session, job_id: str, text_sha256: str) -> JdSnapshot | None:
    """Pasting the same text twice is not a new revision."""
    statement = select(JdSnapshot).where(
        JdSnapshot.job_id == job_id, JdSnapshot.text_sha256 == text_sha256
    )
    return session.scalars(statement).first()


def get_sync_state(session: Session, source: str) -> JobSyncState | None:
    return session.get(JobSyncState, source)


def touch_sync_state(session: Session, source: str, synced_at: datetime) -> None:
    """Upsert: the first sync inserts the row, later syncs move the timestamp."""
    state = session.get(JobSyncState, source)
    if state is None:
        session.add(JobSyncState(source=source, synced_at=synced_at))
    else:
        state.synced_at = synced_at
