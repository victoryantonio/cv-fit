"""Shared vocabulary for the two guards: results, contexts, and small primitives.

Both the suggestion guard (S6) and the cover note guard (S8) speak the same
language: a rule returns a `Violation` or nothing, `GuardResult` is what gets
stored, and both consult a context that holds CV evidence and never raw JD prose.
Keeping that language in one place is what lets the two rule lists stay honest
about running over the same primitives.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.analysis.enums import Verdict
from app.shared.text import words

NUMBER_NOT_IN_CV = "numbers_not_in_cv"
UNKNOWN_VOCABULARY = "unknown_vocabulary"
GAP_NOTE_HAS_REWRITE = "gap_note_has_rewrite"
ORIGINAL_NOT_IN_CV = "original_not_in_cv"
BANNED_PHRASE = "banned_phrase"

_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9+#/.\-]*")
_SEGMENT = re.compile(r"[^\n.;:•|]+")

#: Empty claims and significance inflation, per AGENTS.md and `suggest.v1.md`.
BANNED = (
    "results-driven",
    "passionate",
    "team player",
    "proven track record",
    "dynamic professional",
    "spearheaded",
    "revolutionised",
    "revolutionized",
    "world-class",
)

#: Capitalised words that carry no factual claim, so they need no CV source.
INNOCENT = frozenset(
    {
        "i",
        "my",
        "our",
        "we",
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
        "jan",
        "feb",
        "mar",
        "apr",
        "jun",
        "jul",
        "aug",
        "sep",
        "sept",
        "oct",
        "nov",
        "dec",
        "monday",
        "tuesday",
        "wednesday",
        "thursday",
        "friday",
        "saturday",
        "sunday",
    }
)


@dataclass(frozen=True)
class Violation:
    """The rule that fired, plus a short reason we can store without CV text."""

    code: str
    detail: str


@dataclass(frozen=True)
class GuardResult:
    status: str
    code: str | None = None
    detail: str | None = None

    @property
    def ok(self) -> bool:
        return self.code is None


def rejected(code: str) -> str:
    """The stored form: `rejected_<rule>`."""
    return f"rejected_{code}"


def numbers_in(text: str) -> frozenset[str]:
    """Every numeric token in the text, with thousands separators removed."""
    return frozenset(match.replace(",", "") for match in _NUMBER.findall(text))


@dataclass(frozen=True)
class GuardContext:
    """What a rule may look at: CV evidence only, never the raw JD."""

    cv_text: str
    skills_text: str = ""
    verdict: Verdict | None = None

    @classmethod
    def build(
        cls,
        *,
        cv_text: str,
        section_texts: dict[str, str] | None = None,
        verdict: Verdict | None = None,
    ) -> GuardContext:
        skills = (section_texts or {}).get("skills", "")
        return cls(cv_text=cv_text, skills_text=skills, verdict=verdict)

    def vocabulary(self) -> frozenset[str]:
        return frozenset(words(self.cv_text) + words(self.skills_text))

    def numbers(self) -> frozenset[str]:
        return numbers_in(self.cv_text + " " + self.skills_text)


def is_grounded(token: str, known: frozenset[str]) -> bool:
    """`CI/CD` counts as known when the CV says both `CI` and `CD`."""
    if token in known:
        return True
    parts = [part for part in re.split(r"[^a-z0-9]+", token) if part]
    return bool(parts) and all(part in known for part in parts)


def _is_named(token: str) -> bool:
    """Acronyms and versioned product names claim facts; a capital letter may not."""
    if token.casefold() in INNOCENT:
        return False
    if any(char.isdigit() for char in token):
        return True
    return token.isupper() and 2 <= len(token) <= 8


def suspects(text: str) -> list[str]:
    """Casefolded tokens that look like names, tools or certifications."""
    found: list[str] = []
    for segment in _SEGMENT.findall(text):
        tokens = list(_TOKEN.finditer(segment))
        # A one-word proposal has no sentence to open, so its capital is a claim.
        alone = len(tokens) == 1
        for match in tokens:
            token = match.group(0).rstrip(".,;:)!?'\"")
            if not token or not token[0].isupper():
                continue
            named = _is_named(token)
            if match.start() == 0 and not named and not alone:
                continue
            found.append(token.casefold())
    return found


@dataclass(frozen=True)
class CoverClaim:
    """One confirmed match the note may assert, with the quote behind it."""

    index: int
    requirement: str
    quote: str


#: Greeting and role words: they address a slot, they do not name a person.
ADDRESS = frozenset(
    {
        "best",
        "dear",
        "hello",
        "hey",
        "hi",
        "hiring",
        "madam",
        "manager",
        "recruiter",
        "regards",
        "sincerely",
        "sir",
        "team",
        "thank",
        "thanks",
        "there",
    }
)


@dataclass(frozen=True)
class CoverContext:
    """Everything S8 may consult: verified evidence, never the raw JD prose."""

    guard: GuardContext
    strong: tuple[CoverClaim, ...] = ()
    open_keywords: frozenset[str] = frozenset()
    reserved: frozenset[str] = frozenset()
    min_words: int = 60
    max_words: int = 150

    def vocabulary(self) -> frozenset[str]:
        # Pronouns and month names open a sentence mid-note the way they never do
        # inside a CV bullet, and neither carries a factual claim.
        return self.guard.vocabulary() | self.reserved | ADDRESS | INNOCENT

    def numbers(self) -> frozenset[str]:
        return self.guard.numbers()
