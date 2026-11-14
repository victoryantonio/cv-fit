"""Job intake: create a job, capture an immutable JD snapshot, triage the status.

Snapshots are never edited. Pasting changed text creates a new row, so an old
analysis keeps the text it was judged against (F05). The heuristics in
`jd_input` only annotate a snapshot; they never reject the paste.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.modules.jobs import queries, sync
from app.modules.jobs.enums import JobOutcome, JobSource, JobStatus, SnapshotSourceKind
from app.modules.jobs.jd_input import detect_injection, detect_truncation
from app.modules.jobs.models import JdSnapshot, JobPosting
from app.modules.jobs.ports import JobAlertSource
from app.modules.jobs.prefilter import PrefilterCriteria
from app.modules.jobs.validation import (
    ALLOWED_TRANSITIONS,
    MAX_COMPANY_CHARS,
    MAX_LOCATION_CHARS,
    MAX_URL_CHARS,
    check_choice,
    check_length,
    clean,
    no_criteria,
    required_title,
)
from app.shared.clock import Clock
from app.shared.errors import AppError
from app.shared.text import sha256_hex


@dataclass(frozen=True, slots=True)
class JobService:
    session_factory: sessionmaker[Session]
    clock: Clock
    #: None until the Gmail helper is wired; sync then reports GMAIL_NOT_CONNECTED.
    alert_source: JobAlertSource | None = None
    criteria: Callable[[], PrefilterCriteria] = no_criteria

    async def sync_alerts(
        self, *, since: datetime | None = None, limit: int = 25
    ) -> dict[str, Any]:
        """Pull alert emails through the helper and store the jobs (FR-06)."""
        if self.alert_source is None:
            raise AppError(
                "GMAIL_NOT_CONNECTED",
                "No Gmail alert source is configured.",
                {"hint": "set GMAIL_CLIENT_SECRET_PATH and run: python -m app.mcp_gmail auth"},
            )
        report = await sync.sync_alerts(
            session_factory=self.session_factory,
            clock=self.clock,
            source=self.alert_source,
            criteria=self.criteria(),
            since=since,
            limit=limit,
        )
        return report.as_dict()

    def last_sync(self) -> dict[str, Any]:
        """When alerts were last pulled, so the UI can say "no new alerts since ..."."""
        with self.session_factory() as session:
            state = queries.get_sync_state(session, sync.SYNC_SOURCE)
        return {
            "source": sync.SYNC_SOURCE,
            "synced_at": state.synced_at if state is not None else None,
        }

    def create(
        self,
        *,
        title: str,
        company: str | None = None,
        url: str | None = None,
        location: str | None = None,
    ) -> dict[str, Any]:
        with self.session_factory() as session:
            job = JobPosting(
                source=JobSource.MANUAL,
                title=required_title(title),
                company=clean(company, field="company", max_chars=MAX_COMPANY_CHARS),
                location=clean(location, field="location", max_chars=MAX_LOCATION_CHARS),
                url=clean(url, field="url", max_chars=MAX_URL_CHARS),
                status=JobStatus.NEW,
                outcome=JobOutcome.NONE,
                created_at=self.clock.now(),
            )
            session.add(job)
            session.commit()
            return self._job_payload(job)

    def list(self, *, status: str | None = None, filtered: bool | None = None) -> dict[str, Any]:
        """`filtered=True` lists what the pre-filter set aside; None lists everything."""
        if status is not None:
            check_choice(status, tuple(JobStatus), field="status")
        with self.session_factory() as session:
            jobs = queries.list_jobs(session, status=status, filtered=filtered)
            grouped = queries.snapshots_by_job(session, [job.id for job in jobs])
            items = [
                {
                    **self._job_payload(job),
                    "snapshot_count": len(grouped[job.id]),
                    "latest_snapshot_id": grouped[job.id][0].id if grouped[job.id] else None,
                }
                for job in jobs
            ]
        return {"items": items, "total": len(items)}

    def get(self, job_id: str) -> dict[str, Any]:
        with self.session_factory() as session:
            job = self._load_job(session, job_id)
            snapshots = queries.list_snapshots(session, job_id)
            return {
                **self._job_payload(job),
                "snapshots": [self._snapshot_payload(snapshot) for snapshot in snapshots],
            }

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        outcome: str | None = None,
        applied_at: datetime | None = None,
        keep: bool | None = None,
    ) -> dict[str, Any]:
        """`keep=True` is the user overriding the pre-filter on one job."""
        with self.session_factory() as session:
            job = self._load_job(session, job_id)
            if keep:
                job.filter_reason = None
            if status is not None:
                check_choice(status, tuple(JobStatus), field="status")
                if status != job.status and status not in ALLOWED_TRANSITIONS.get(
                    job.status, frozenset()
                ):
                    raise AppError(
                        "VALIDATION_ERROR",
                        f"A job cannot go from {job.status} to {status}.",
                        {"field": "status", "from": job.status, "to": status},
                    )
                job.status = status
                if status == JobStatus.APPLIED and job.applied_at is None:
                    job.applied_at = applied_at or self.clock.now()
            if outcome is not None:
                job.outcome = check_choice(outcome, tuple(JobOutcome), field="outcome")
            if applied_at is not None:
                job.applied_at = applied_at
            session.commit()
            return self._job_payload(job)

    def add_snapshot(
        self,
        job_id: str,
        *,
        raw_text: str,
        source_kind: str,
    ) -> dict[str, Any]:
        kind = check_choice(source_kind, tuple(SnapshotSourceKind), field="source_kind")
        check_length(raw_text)
        text_sha256 = sha256_hex(raw_text)
        with self.session_factory() as session:
            self._load_job(session, job_id)
            existing = queries.find_snapshot(session, job_id, text_sha256)
            if existing is not None:
                return {**self._snapshot_payload(existing), "reused": True}
            snapshot = JdSnapshot(
                job_id=job_id,
                source_kind=kind,
                raw_text=raw_text,
                text_sha256=text_sha256,
                injection_flags=detect_injection(raw_text),
                truncation_warning=bool(detect_truncation(raw_text)),
                captured_at=self.clock.now(),
            )
            session.add(snapshot)
            session.commit()
            return {**self._snapshot_payload(snapshot), "reused": False}

    def snapshot(self, snapshot_id: str) -> dict[str, Any]:
        """Snapshot with its text. Callers inside the backend own that text."""
        with self.session_factory() as session:
            snapshot = queries.get_snapshot(session, snapshot_id)
            if snapshot is None:
                raise AppError(
                    "NOT_FOUND", "That JD snapshot does not exist.", {"snapshot_id": snapshot_id}
                )
            return {
                **self._snapshot_payload(snapshot),
                "job_id": snapshot.job_id,
                "raw_text": snapshot.raw_text,
            }

    def snapshot_ids(self, job_id: str) -> Sequence[str]:
        """Just the ids, so another module never needs the jobs' table rows."""
        with self.session_factory() as session:
            self._load_job(session, job_id)
            return [snapshot.id for snapshot in queries.list_snapshots(session, job_id)]

    def job_brief_for_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        """Owner, title and company only. Callers that want the text must ask for it."""
        with self.session_factory() as session:
            snapshot = queries.get_snapshot(session, snapshot_id)
            if snapshot is None:
                return None
            job = queries.get_job(session, snapshot.job_id)
            if job is None:
                return {"id": snapshot.job_id, "title": None, "company": None}
            return {"id": job.id, "title": job.title, "company": job.company}

    def mark_analyzed(self, job_id: str) -> None:
        """Called by the pipeline once an analysis is stored (F06)."""
        with self.session_factory() as session:
            job = queries.get_job(session, job_id)
            if job is None or job.status == JobStatus.APPLIED:
                return
            job.status = JobStatus.ANALYZED
            session.commit()

    def _load_job(self, session: Session, job_id: str) -> JobPosting:
        job = queries.get_job(session, job_id)
        if job is None:
            raise AppError("NOT_FOUND", "That job does not exist.", {"job_id": job_id})
        return job

    @staticmethod
    def _job_payload(job: JobPosting) -> dict[str, Any]:
        return {
            "id": job.id,
            "source": job.source,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "url": job.url,
            "status": job.status,
            "outcome": job.outcome,
            "applied_at": job.applied_at,
            "filter_reason": job.filter_reason,
            "received_at": job.received_at,
            "created_at": job.created_at,
        }

    @staticmethod
    def _snapshot_payload(snapshot: JdSnapshot) -> dict[str, Any]:
        return {
            "id": snapshot.id,
            "source_kind": snapshot.source_kind,
            "text_sha256": snapshot.text_sha256,
            "chars": len(snapshot.raw_text),
            "injection_flags": list(snapshot.injection_flags or []),
            "truncation_warning": snapshot.truncation_warning,
            "truncation_reasons": detect_truncation(snapshot.raw_text),
            "captured_at": snapshot.captured_at,
        }


