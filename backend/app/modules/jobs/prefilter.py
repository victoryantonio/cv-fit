"""Pre-filter for synced alerts (FR-07).

Each rule is a function in `RULES`. A new rule is appended, never woven into the
engine. A job is never deleted: the first rule that objects supplies the reason
stored on the row, and the user can still find the job and override it.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from app.modules.jobs.ports import AlertCard

MAX_REASON_CHARS: Final = 200  # job_posting.filter_reason is String(200)

#: Levels recognised in a title. Absence of any level is not a reason to filter:
#: an unlabelled title is unknown, and unknown is not a reason to hide a job.
SENIORITY_LEVELS: Final[tuple[str, ...]] = (
    "intern",
    "junior",
    "mid",
    "senior",
    "staff",
    "principal",
    "lead",
    "head",
    "director",
    "vp",
    "chief",
    "manager",
)

_WORD = re.compile(r"[a-z]+")


@dataclass(frozen=True, slots=True)
class PrefilterCriteria:
    include_keywords: tuple[str, ...] = ()
    exclude_keywords: tuple[str, ...] = ()
    locations: tuple[str, ...] = ()
    seniority: tuple[str, ...] = ()

    @classmethod
    def from_settings(cls, payload: Mapping[str, Any]) -> PrefilterCriteria:
        """Build from `settings_service.read()["criteria"]`, ignoring junk values."""

        def entries(key: str) -> tuple[str, ...]:
            values = payload.get(key) or ()
            if not isinstance(values, (list, tuple)):
                return ()
            return tuple(str(value).strip() for value in values if str(value).strip())

        return cls(
            include_keywords=entries("include_keywords"),
            exclude_keywords=entries("exclude_keywords"),
            locations=entries("locations"),
            seniority=entries("seniority"),
        )


Rule = Callable[[AlertCard, PrefilterCriteria], str | None]


def _haystack(card: AlertCard) -> str:
    """Title and company only: the location has its own rule."""
    return " ".join(part for part in (card.title, card.company) if part).lower()


def _words(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def excluded_keyword(card: AlertCard, criteria: PrefilterCriteria) -> str | None:
    haystack = _haystack(card)
    for keyword in criteria.exclude_keywords:
        if keyword.lower() in haystack:
            return f'excluded keyword: "{keyword}"'
    return None


def no_include_keyword(card: AlertCard, criteria: PrefilterCriteria) -> str | None:
    if not criteria.include_keywords:
        return None
    haystack = _haystack(card)
    if any(keyword.lower() in haystack for keyword in criteria.include_keywords):
        return None
    return "no include keyword matched"


def location_not_allowed(card: AlertCard, criteria: PrefilterCriteria) -> str | None:
    if not criteria.locations or not card.location:
        return None
    wanted = card.location.lower()
    if any(allowed.lower() in wanted for allowed in criteria.locations):
        return None
    return f'location not allowed: "{card.location}"'


def seniority_not_allowed(card: AlertCard, criteria: PrefilterCriteria) -> str | None:
    if not criteria.seniority:
        return None
    allowed = {level.lower() for level in criteria.seniority}
    found = _words(card.title).intersection(SENIORITY_LEVELS)
    if not found or found & allowed:
        return None
    return f'seniority not allowed: "{sorted(found)[0]}"'


#: Order matters: the cheapest and most explicit reason wins.
RULES: Final[tuple[Rule, ...]] = (
    excluded_keyword,
    no_include_keyword,
    location_not_allowed,
    seniority_not_allowed,
)


def evaluate(card: AlertCard, criteria: PrefilterCriteria) -> str | None:
    """The first reason this card should be set aside, or None when it is kept."""
    for rule in RULES:
        reason = rule(card, criteria)
        if reason is not None:
            return reason[:MAX_REASON_CHARS]
    return None
