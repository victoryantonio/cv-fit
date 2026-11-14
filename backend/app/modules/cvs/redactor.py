"""PII redaction, applied before any text leaves the machine.

Rules are plain functions applied in a fixed order. Adding a rule means appending
to `RULES`; the engine below never changes. Tokens are numbered per kind in order
of first appearance, so the same input always produces the same output.

False negatives are worse than false positives here (AGENTS.md), so the street
address rule redacts a whole line and the phone rule prefers to over-redact.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Final

Counts = dict[str, int]
Rule = Callable[[str, Counts], str]

_EMAIL: Final = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# A phone number needs a separator, a country marker, or at least 10 digits.
# That keeps "2020-2024" a date range instead of a phone number.
_PHONE_CANDIDATE: Final = re.compile(r"\+?\d[\d\s().\-]{6,20}\d")

_PERSONAL_URL: Final = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(?:linkedin\.com|github\.com|gitlab\.com|x\.com|twitter\.com|medium\.com"
    r"|behance\.net|dribbble\.com|stackoverflow\.com)"
    r"/[^\s<>\"')]+",
    re.IGNORECASE,
)

# Indonesian NIK, credit-card style groupings, and 16 bare digits.
_NATIONAL_ID: Final = re.compile(r"\b(?:\d{16}|\d{4}[ \-]\d{4}[ \-]\d{4}[ \-]\d{4})\b")

_ADDRESS_KEYWORDS: Final = (
    "jl",
    "jl.",
    "jalan",
    "street",
    "st.",
    "road",
    "rd.",
    "avenue",
    "ave.",
    "boulevard",
    "blvd",
    "lane",
    "alley",
    "gang",
    "gg.",
    "blok",
    "block",
    "rt/rw",
    "kelurahan",
    "kecamatan",
    "kabupaten",
    "provinsi",
    "zip",
    "postal code",
)


def _token(counts: Counts, kind: str) -> str:
    counts[kind] = counts.get(kind, 0) + 1
    return f"[{kind}_{counts[kind]}]"


def rule_email(text: str, counts: Counts) -> str:
    return _EMAIL.sub(lambda _match: _token(counts, "EMAIL"), text)


def rule_phone(text: str, counts: Counts) -> str:
    def replace(match: re.Match[str]) -> str:
        candidate = match.group(0)
        digits = re.sub(r"\D", "", candidate)
        if not 9 <= len(digits) <= 15:
            return candidate
        has_marker = any(marker in candidate for marker in ("+", "(", ")"))
        if not has_marker and len(digits) < 10:
            return candidate
        return _token(counts, "PHONE")

    return _PHONE_CANDIDATE.sub(replace, text)


def rule_personal_url(text: str, counts: Counts) -> str:
    return _PERSONAL_URL.sub(lambda _match: _token(counts, "URL"), text)


def rule_national_id(text: str, counts: Counts) -> str:
    return _NATIONAL_ID.sub(lambda _match: _token(counts, "ID"), text)


def _looks_like_address(line: str) -> bool:
    stripped = line.strip()
    if not 8 <= len(stripped) <= 160:
        return False
    lowered = stripped.lower()
    if not any(char.isdigit() for char in lowered):
        return False
    return any(keyword in lowered for keyword in _ADDRESS_KEYWORDS)


def rule_street_address(text: str, counts: Counts) -> str:
    lines = [
        _token(counts, "ADDRESS") if _looks_like_address(line) else line
        for line in text.split("\n")
    ]
    return "\n".join(lines)


RULES: tuple[Rule, ...] = (
    rule_email,
    rule_phone,
    rule_personal_url,
    rule_national_id,
    rule_street_address,
)


def custom_terms_rule(terms: Sequence[str]) -> Rule:
    """User-supplied literals (FR-24). Longest first so "PT Contoh Jaya" wins."""
    ordered = sorted({term.strip() for term in terms if term.strip()}, key=len, reverse=True)
    pattern = (
        re.compile("|".join(re.escape(term) for term in ordered), re.IGNORECASE)
        if ordered
        else None
    )

    def rule(text: str, counts: Counts) -> str:
        if pattern is None:
            return text
        return pattern.sub(lambda _match: _token(counts, "CUSTOM"), text)

    return rule


@dataclass(frozen=True, slots=True)
class RedactionResult:
    text: str
    counts: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact(text: str, *, custom_terms: Sequence[str] = ()) -> RedactionResult:
    counts: Counts = {}
    rules: tuple[Rule, ...] = (*RULES, custom_terms_rule(custom_terms))
    for rule in rules:
        text = rule(text, counts)
    return RedactionResult(text=text, counts=counts)
