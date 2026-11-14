"""Ports the jobs module depends on.

The Gmail helper is one process away, so it is reached through this Protocol and
not imported: a sync test uses a fake source and never spawns anything. The
helper parses alert emails because only it knows their layout; the backend
receives job cards and owns normalization, deduplication and pre-filtering.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol


class AlertSourceError(Exception):
    """The helper is unreachable, not authorised, or could not read an email.

    `code` is one of the stable API codes (GMAIL_NOT_CONNECTED,
    GMAIL_AUTH_EXPIRED, ALERT_PARSE_FAILED) so the caller can re-raise it as an
    AppError without inspecting the message text.
    """

    def __init__(self, message: str, *, code: str = "GMAIL_NOT_CONNECTED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AlertMessage:
    """A pointer to one alert email. The body stays in the helper until asked."""

    message_id: str
    received_at: datetime


@dataclass(frozen=True, slots=True)
class AlertCard:
    """One job as it appeared in an alert email, before any normalization."""

    title: str
    company: str | None = None
    location: str | None = None
    url: str | None = None


@dataclass(frozen=True, slots=True)
class AlertDetail:
    message_id: str
    received_at: datetime
    cards: list[AlertCard] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class JobAlertSource(Protocol):
    async def list_alerts(self, *, since: datetime | None, limit: int) -> list[AlertMessage]: ...

    async def fetch_alert(self, message_id: str) -> AlertDetail: ...
