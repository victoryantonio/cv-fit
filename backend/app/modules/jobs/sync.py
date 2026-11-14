"""Turn alert cards into job rows: normalize, deduplicate, pre-filter (FR-06, FR-07).

Every card from every email is decided once, in one transaction, so a second run
over the same emails adds nothing. A card that cannot become a job is reported
by message id; nothing is dropped silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Final
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.orm import Session, sessionmaker

from app.modules.jobs import prefilter, queries
from app.modules.jobs.enums import JobOutcome, JobSource, JobStatus
from app.modules.jobs.models import JobPosting
from app.modules.jobs.ports import AlertCard, AlertMessage, AlertSourceError, JobAlertSource
from app.shared.clock import Clock
from app.shared.errors import AppError

MAX_TITLE_CHARS: Final = 200
MAX_COMPANY_CHARS: Final = 200
MAX_LOCATION_CHARS: Final = 200
MAX_URL_CHARS: Final = 1000
MAX_SYNC_LIMIT: Final = 50

#: The only alert source today; the column exists so a second one needs no migration.
SYNC_SOURCE: Final = "gmail"

#: Codes that stop the whole sync. A parse failure only skips one email.
FATAL_SOURCE_CODES: Final[frozenset[str]] = frozenset({"GMAIL_NOT_CONNECTED", "GMAIL_AUTH_EXPIRED"})

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class SyncReport:
    messages: int
    new: int
    duplicate: int
    filtered: int
    parse_failed: list[str] = field(default_factory=list)
    synced_at: datetime | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "messages": self.messages,
            "new": self.new,
            "duplicate": self.duplicate,
            "filtered": self.filtered,
            "parse_failed": list(self.parse_failed),
            "synced_at": self.synced_at,
        }


def _collapse(value: str | None, *, max_chars: int) -> str | None:
    """Remote text is normalized, never rejected: a long title is truncated."""
    if value is None:
        return None
    cleaned = _WHITESPACE.sub(" ", value).strip()
    if not cleaned:
        return None
    return cleaned[:max_chars]


def canonical_url(url: str | None) -> str | None:
    """Drop tracking parameters so the same job dedupes across emails.

    Alerts carry per-recipient tracking ids in the query string; two emails that
    point at the same posting must produce the same key.
    """
    cleaned = _collapse(url, max_chars=MAX_URL_CHARS * 2)
    if cleaned is None:
        return None
    parts = urlsplit(cleaned)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return cleaned[:MAX_URL_CHARS]
    host = parts.hostname.lower().removeprefix("www.")
    path = parts.path
    if host.endswith("linkedin.com"):
        path = path.removeprefix("/comm")
    canonical = urlunsplit((parts.scheme, host, path, "", ""))
    return canonical[:MAX_URL_CHARS]


def _build_job(
    card: AlertCard,
    *,
    message_id: str,
    received_at: datetime,
    reason: str | None,
    now: datetime,
) -> JobPosting | None:
    title = _collapse(card.title, max_chars=MAX_TITLE_CHARS)
    if title is None:
        return None
    return JobPosting(
        source=JobSource.GMAIL_ALERT,
        email_message_id=message_id,
        title=title,
        company=_collapse(card.company, max_chars=MAX_COMPANY_CHARS),
        location=_collapse(card.location, max_chars=MAX_LOCATION_CHARS),
        url=canonical_url(card.url),
        status=JobStatus.NEW,
        outcome=JobOutcome.NONE,
        filter_reason=reason,
        received_at=received_at,
        created_at=now,
    )


def _already_known(
    session: Session, job: JobPosting, *, seen_urls: set[str], seen_titles: set[tuple[str, str]]
) -> bool:
    """URL is the identity when there is one; otherwise the email plus its title."""
    if job.url:
        if job.url in seen_urls or queries.find_job_by_url(session, job.url) is not None:
            return True
        seen_urls.add(job.url)
        return False
    key = (job.email_message_id or "", job.title)
    if key in seen_titles:
        return True
    seen_titles.add(key)
    return queries.find_job_by_message_and_title(session, key[0], key[1]) is not None


@dataclass
class _Tally:
    """Running counts for one sync, mutated as cards are accepted."""

    new: int = 0
    duplicate: int = 0
    filtered: int = 0
    parse_failed: list[str] = field(default_factory=list)

    def failed(self, message_id: str) -> None:
        """One entry per message, however many of its cards were unusable."""
        if message_id not in self.parse_failed:
            self.parse_failed.append(message_id)


@dataclass
class _Seen:
    """What this run already accepted, so one email's repeats do not double-add."""

    urls: set[str] = field(default_factory=set)
    titles: set[tuple[str, str]] = field(default_factory=set)


async def sync_alerts(
    *,
    session_factory: sessionmaker[Session],
    clock: Clock,
    source: JobAlertSource,
    criteria: prefilter.PrefilterCriteria,
    since: datetime | None = None,
    limit: int = 25,
) -> SyncReport:
    _check_limit(limit)
    try:
        messages = await source.list_alerts(since=since, limit=limit)
    except AlertSourceError as exc:
        raise AppError(exc.code, str(exc), {"source": "gmail"}) from exc

    tally = _Tally()
    seen = _Seen()
    now = clock.now()
    with session_factory() as session:
        for message in messages:
            await _ingest_message(
                session,
                source=source,
                message=message,
                criteria=criteria,
                now=now,
                tally=tally,
                seen=seen,
            )
        queries.touch_sync_state(session, SYNC_SOURCE, now)
        session.commit()
    return SyncReport(
        messages=len(messages),
        new=tally.new,
        duplicate=tally.duplicate,
        filtered=tally.filtered,
        parse_failed=tally.parse_failed,
        synced_at=now,
    )


def _check_limit(limit: int) -> None:
    if not 1 <= limit <= MAX_SYNC_LIMIT:
        raise AppError(
            "VALIDATION_ERROR",
            f"limit must be between 1 and {MAX_SYNC_LIMIT}.",
            {"field": "limit", "max": MAX_SYNC_LIMIT},
        )


async def _ingest_message(
    session: Session,
    *,
    source: JobAlertSource,
    message: AlertMessage,
    criteria: prefilter.PrefilterCriteria,
    now: datetime,
    tally: _Tally,
    seen: _Seen,
) -> None:
    """One email. A parse failure skips this email only; an auth failure stops."""
    try:
        detail = await source.fetch_alert(message.message_id)
    except AlertSourceError as exc:
        if exc.code in FATAL_SOURCE_CODES:
            raise AppError(exc.code, str(exc), {"source": "gmail"}) from exc
        tally.failed(message.message_id)
        return
    if not detail.cards:
        tally.failed(message.message_id)
        return
    for card in detail.cards:
        _ingest_card(
            session,
            card=card,
            message_id=message.message_id,
            received_at=detail.received_at,
            criteria=criteria,
            now=now,
            tally=tally,
            seen=seen,
        )


def _ingest_card(
    session: Session,
    *,
    card: AlertCard,
    message_id: str,
    received_at: datetime,
    criteria: prefilter.PrefilterCriteria,
    now: datetime,
    tally: _Tally,
    seen: _Seen,
) -> None:
    job = _build_job(
        card,
        message_id=message_id,
        received_at=received_at,
        reason=prefilter.evaluate(card, criteria),
        now=now,
    )
    if job is None:
        tally.failed(message_id)
        return
    if _already_known(session, job, seen_urls=seen.urls, seen_titles=seen.titles):
        tally.duplicate += 1
        return
    session.add(job)
    session.flush()
    tally.new += 1
    if job.filter_reason is not None:
        tally.filtered += 1
