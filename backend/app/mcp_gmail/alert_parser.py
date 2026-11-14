"""Parsers for job-alert emails as they actually arrive.

Each layout is a function in `PARSERS`. A parser returns None when the email is
not its layout, so the engine can try the next one; a layout nobody recognises
is reported with its message id instead of being dropped (E05).

The card anchor is the "View job:" line, and the card is read backwards from it,
because the first block of a digest also carries the digest header.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Final

MAX_CARDS: Final = 100

_SEPARATOR = re.compile(r"^\s*-{10,}\s*$")
_VIEW_JOB = re.compile(r"^\s*View job:\s*(\S+)\s*$", re.IGNORECASE)
_NOISE: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"^your job alert for\b", re.IGNORECASE),
    re.compile(r"new jobs? match your preferences", re.IGNORECASE),
    re.compile(r"\balum", re.IGNORECASE),
    re.compile(r"actively hiring", re.IGNORECASE),
    re.compile(r"actively reviewing", re.IGNORECASE),
    re.compile(r"^apply with\b", re.IGNORECASE),
    re.compile(r"^easy apply\b", re.IGNORECASE),
    re.compile(r"early applicant", re.IGNORECASE),
    re.compile(r"^promoted$", re.IGNORECASE),
    re.compile(r"^\d+\s+company alum", re.IGNORECASE),
    re.compile(r"^\d+\s+connections?$", re.IGNORECASE),
    re.compile(r"^responds\b", re.IGNORECASE),
)


@dataclass(frozen=True, slots=True)
class ParsedCard:
    title: str
    company: str | None = None
    location: str | None = None
    url: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
        }


@dataclass(frozen=True, slots=True)
class ParseResult:
    cards: list[ParsedCard] = field(default_factory=list)
    layout: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def recognized(self) -> bool:
        return self.layout is not None

    def as_dict(self) -> dict[str, Any]:
        return {
            "layout": self.layout,
            "cards": [card.as_dict() for card in self.cards],
            "warnings": list(self.warnings),
        }


def _is_noise(line: str) -> bool:
    return any(pattern.search(line) for pattern in _NOISE)


def _card_from_block(lines: list[str]) -> ParsedCard | None:
    """Read the three lines above "View job:" as title, company, location."""
    anchor: int | None = None
    url: str | None = None
    for index, line in enumerate(lines):
        match = _VIEW_JOB.match(line)
        if match:
            anchor, url = index, match.group(1)
            break
    if anchor is None or url is None:
        return None
    candidates = [line for line in lines[:anchor] if line and not _is_noise(line)]
    if not candidates:
        return None
    tail = candidates[-3:]
    return ParsedCard(
        title=tail[0],
        company=tail[1] if len(tail) > 1 else None,
        location=tail[2] if len(tail) > 2 else None,
        url=url,
    )


def parse_linkedin_digest(_subject: str, body: str) -> list[ParsedCard] | None:
    """LinkedIn Job Alerts: a header, then cards separated by a dashed rule."""
    lines = body.splitlines()
    if not any("job alert" in line.lower() for line in lines[:6]):
        return None
    cards: list[ParsedCard] = []
    block: list[str] = []
    for line in [*lines, "-" * 20]:  # the sentinel closes the last block
        if _SEPARATOR.match(line):
            card = _card_from_block([candidate.strip() for candidate in block])
            if card is not None:
                cards.append(card)
            block = []
            continue
        block.append(line)
    return cards


#: (name, parser). Adding a layout means adding a function, not editing the engine.
PARSERS: Final[tuple[tuple[str, Callable[[str, str], list[ParsedCard] | None]], ...]] = (
    ("linkedin_job_alert_digest", parse_linkedin_digest),
)


def parse_alert(*, subject: str, body: str) -> ParseResult:
    for name, parser in PARSERS:
        cards = parser(subject, body)
        if cards is None:
            continue
        if not cards:
            return ParseResult(layout=name, warnings=["no job card found in this email"])
        return ParseResult(cards=cards[:MAX_CARDS], layout=name)
    return ParseResult(warnings=["unknown alert layout"])
