"""S6: the rules a CV suggestion must survive before it is shown.

A rule is `(suggestion, context) -> Violation | None`; `RULES` is the list the
engine walks, so adding a rule is adding a list entry. The guard is deliberately
blunt: rejecting a fair suggestion is cheaper than letting one invented number,
tool or employer through. Nothing here calls an LLM.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.modules.analysis.enums import SuggestionType, Verdict
from app.modules.analysis.guard_types import (
    BANNED,
    BANNED_PHRASE,
    GAP_NOTE_HAS_REWRITE,
    NUMBER_NOT_IN_CV,
    ORIGINAL_NOT_IN_CV,
    UNKNOWN_VOCABULARY,
    GuardContext,
    Violation,
    is_grounded,
    numbers_in,
    suspects,
)
from app.modules.analysis.schemas import SuggestionOut
from app.shared.text import contains_quote, normalise


def rule_numbers(suggestion: SuggestionOut, context: GuardContext) -> Violation | None:
    """Rule 1: every number in the rewrite already exists in the CV."""
    body = suggestion.proposed_text or ""
    unknown = sorted(numbers_in(body) - context.numbers())
    if not unknown:
        return None
    return Violation(NUMBER_NOT_IN_CV, f"numbers absent from the CV: {', '.join(unknown)}")


def rule_gap_note(suggestion: SuggestionOut, context: GuardContext) -> Violation | None:
    """Rule 3: a gap_note names a gap and never carries rewrite text."""
    if suggestion.type is not SuggestionType.GAP_NOTE:
        return None
    if (suggestion.proposed_text or "").strip():
        return Violation(GAP_NOTE_HAS_REWRITE, "gap_note carried rewrite text")
    return None


def rule_original(suggestion: SuggestionOut, context: GuardContext) -> Violation | None:
    """A rewrite must edit a line that really exists in the CV."""
    original = (suggestion.original_text or "").strip()
    if not original or contains_quote(context.cv_text, original):
        return None
    return Violation(ORIGINAL_NOT_IN_CV, "original_text is not a verbatim CV line")


def rule_banned(suggestion: SuggestionOut, context: GuardContext) -> Violation | None:
    """Empty claims and inflation are rejected without judgement calls."""
    body = normalise(f"{suggestion.proposed_text or ''} {suggestion.rationale}")
    for phrase in BANNED:
        pattern = rf"(?<![a-z]){re.escape(phrase)}(?![a-z])"
        if re.search(pattern, body):
            return Violation(BANNED_PHRASE, f"banned phrase: {phrase}")
    return None


def rule_vocabulary(suggestion: SuggestionOut, context: GuardContext) -> Violation | None:
    """Rule 2: proper nouns, tools and certifications must come from the CV.

    An `add_keyword` suggestion is the one exception, and only when the
    requirement it adds the keyword for is already grounded in the CV.
    """
    if suggestion.type is SuggestionType.ADD_KEYWORD and context.verdict in {
        Verdict.STRONG,
        Verdict.PARTIAL,
    }:
        return None
    known = context.vocabulary()
    unknown = [
        token for token in suspects(suggestion.proposed_text or "") if not is_grounded(token, known)
    ]
    if not unknown:
        return None
    return Violation(
        UNKNOWN_VOCABULARY,
        f"vocabulary absent from the CV: {', '.join(sorted(set(unknown)))}",
    )


Rule = Callable[[SuggestionOut, GuardContext], Violation | None]

#: Order is the contract: the first violation is the one that gets stored.
RULES: tuple[Rule, ...] = (
    rule_gap_note,
    rule_original,
    rule_numbers,
    rule_banned,
    rule_vocabulary,
)
