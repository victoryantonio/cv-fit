"""The two fabrication guards, kept as one import surface.

`check_suggestion` is S6 and `check_cover_note` is S8. The rules themselves live
in `suggestion_rules.py` and `cover_rules.py`; the names in between are shared and
live in `guard_types.py`. Callers keep importing from here, so where a rule lives
is a private detail and a new rule is still just a list entry.
"""

from __future__ import annotations

from app.modules.analysis.cover_rules import (
    COVER_INDEX_NOT_STRONG,
    COVER_INVENTED_RECIPIENT,
    COVER_LENGTH_OUT_OF_RANGE,
    COVER_NO_CLAIMS,
    COVER_NOT_ENGLISH,
    COVER_NOTE_RULES,
    COVER_OPEN_KEYWORD,
    COVER_QUOTE_NOT_IN_CV,
    COVER_RECOMMENDATION,
    MIN_ENGLISH_MARKERS,
)
from app.modules.analysis.enums import GuardStatus
from app.modules.analysis.guard_types import (
    BANNED_PHRASE,
    GAP_NOTE_HAS_REWRITE,
    NUMBER_NOT_IN_CV,
    ORIGINAL_NOT_IN_CV,
    UNKNOWN_VOCABULARY,
    CoverClaim,
    CoverContext,
    GuardContext,
    GuardResult,
    Violation,
    rejected,
)
from app.modules.analysis.schemas import CoverNoteDraft, SuggestionOut
from app.modules.analysis.suggestion_rules import RULES

__all__ = [
    "BANNED_PHRASE",
    "COVER_INVENTED_RECIPIENT",
    "COVER_INDEX_NOT_STRONG",
    "COVER_LENGTH_OUT_OF_RANGE",
    "COVER_NOT_ENGLISH",
    "COVER_NOTE_RULES",
    "COVER_NO_CLAIMS",
    "COVER_OPEN_KEYWORD",
    "COVER_QUOTE_NOT_IN_CV",
    "COVER_RECOMMENDATION",
    "CoverClaim",
    "CoverContext",
    "GAP_NOTE_HAS_REWRITE",
    "GuardContext",
    "GuardResult",
    "MIN_ENGLISH_MARKERS",
    "NUMBER_NOT_IN_CV",
    "ORIGINAL_NOT_IN_CV",
    "RULES",
    "UNKNOWN_VOCABULARY",
    "Violation",
    "check_cover_note",
    "check_suggestion",
    "rejected",
]


def check_suggestion(suggestion: SuggestionOut, context: GuardContext) -> GuardResult:
    """Run every rule; the first violation wins, so the stored code is stable."""
    for rule in RULES:
        violation = rule(suggestion, context)
        if violation is not None:
            return GuardResult(
                status=rejected(violation.code),
                code=violation.code,
                detail=violation.detail,
            )
    return GuardResult(status=GuardStatus.PASS)


def check_cover_note(note: CoverNoteDraft, context: CoverContext) -> GuardResult:
    """Run every note rule; the first violation wins, so the stored code is stable."""
    for rule in COVER_NOTE_RULES:
        violation = rule(note, context)
        if violation is not None:
            return GuardResult(
                status=rejected(violation.code),
                code=violation.code,
                detail=violation.detail,
            )
    return GuardResult(status=GuardStatus.PASS)
