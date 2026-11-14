"""S8: the rules a cover note must survive (PRD 8.8, rules 1-7).

The note is prose, not a CV bullet, so the rule set is different: a length and a
language gate, then the same number and banned-phrase checks the suggestion
guard uses, then the checks unique to a note - who it addresses, whether the
names in it exist, and whether the claims behind it are the verified ones.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from app.modules.analysis.guard_types import (
    BANNED,
    BANNED_PHRASE,
    NUMBER_NOT_IN_CV,
    UNKNOWN_VOCABULARY,
    CoverContext,
    Violation,
    is_grounded,
    numbers_in,
    suspects,
)
from app.modules.analysis.schemas import CoverNoteDraft
from app.shared.text import contains_quote, normalise, words

COVER_LENGTH_OUT_OF_RANGE = "word_count_out_of_range"
COVER_NOT_ENGLISH = "not_english"
COVER_RECOMMENDATION = "recommendation_language"
COVER_NO_CLAIMS = "no_claims_asserted"
COVER_INDEX_NOT_STRONG = "asserted_index_not_strong"
COVER_QUOTE_NOT_IN_CV = "claim_quote_not_in_cv"
COVER_OPEN_KEYWORD = "asserts_open_requirement"
COVER_INVENTED_RECIPIENT = "invented_recipient"

#: A note under 60 words in English always has more distinct markers than this.
MIN_ENGLISH_MARKERS = 3

_ENGLISH = frozenset(
    {
        "a", "about", "after", "all", "also", "an", "and", "any", "are", "as",
        "at", "be", "been", "before", "being", "both", "but", "by", "can",
        "could", "did", "do", "does", "for", "from", "had", "has", "have", "how",
        "i", "if", "in", "into", "is", "it", "my", "not", "of", "on", "or",
        "our", "over", "she", "should", "so", "some", "than", "that", "the",
        "their", "them", "then", "there", "these", "they", "this", "those",
        "through", "to", "under", "was", "we", "were", "what", "when", "where",
        "which", "while", "who", "will", "with", "would", "you", "your",
    }
)

#: An offer, a verdict or a probability is never something this tool writes.
_RECOMMENDATION = (
    "you should apply",
    "should apply",
    "apply now",
    "apply today",
    "worth applying",
    "do not apply",
    "don't apply",
    "skip this",
    "skip it",
    "chance of",
    "chances of",
    "probability of",
    "likelihood of",
    "perfect fit",
    "great fit",
    "strong candidate",
)

_GREETING = re.compile(
    r"(?:^|\n)\s*(?i:dear|hi|hello|hey)[ ,]+\s*"
    r"([A-Z][A-Za-z'\-]*(?:\s+[A-Z][A-Za-z'\-]*){0,3})",
    re.MULTILINE,
)


def rule_length(note: CoverNoteDraft, context: CoverContext) -> Violation | None:
    """Rule 1: the note is as long as the settings say, no more and no less."""
    count = len(note.text.split())
    if context.min_words <= count <= context.max_words:
        return None
    return Violation(
        COVER_LENGTH_OUT_OF_RANGE,
        f"{count} words, expected {context.min_words}-{context.max_words}",
    )


def rule_language(note: CoverNoteDraft, context: CoverContext) -> Violation | None:
    """Rule 1: the note is written in English, judged by its function words."""
    tokens = words(note.text)
    if not tokens:
        return Violation(COVER_NOT_ENGLISH, "the note is empty")
    markers = {token for token in tokens if token in _ENGLISH}
    if len(markers) >= MIN_ENGLISH_MARKERS:
        return None
    return Violation(COVER_NOT_ENGLISH, "the note does not read as English")


def _phrases_in(body: str, phrases: tuple[str, ...]) -> str | None:
    for phrase in phrases:
        pattern = rf"(?<![a-z]){re.escape(phrase)}(?![a-z])"
        if re.search(pattern, body):
            return phrase
    return None


def rule_recommendation(note: CoverNoteDraft, context: CoverContext) -> Violation | None:
    """AGENTS rule 9: no apply/skip advice and no probability claims, ever."""
    phrase = _phrases_in(normalise(note.text), _RECOMMENDATION)
    if phrase is None:
        return None
    return Violation(COVER_RECOMMENDATION, f"recommendation phrasing: {phrase}")


def rule_banned(note: CoverNoteDraft, context: CoverContext) -> Violation | None:
    """Rule 6: the banned-phrase list is the same one suggestions are held to."""
    phrase = _phrases_in(normalise(note.text), BANNED)
    if phrase is None:
        return None
    return Violation(BANNED_PHRASE, f"banned phrase: {phrase}")


def rule_numbers(note: CoverNoteDraft, context: CoverContext) -> Violation | None:
    """Rule 2: every number in the note already exists in the CV."""
    unknown = sorted(numbers_in(note.text) - context.numbers())
    if not unknown:
        return None
    return Violation(NUMBER_NOT_IN_CV, f"numbers absent from the CV: {', '.join(unknown)}")


def rule_recipient(note: CoverNoteDraft, context: CoverContext) -> Violation | None:
    """Rule 3: a greeting may address a role, never a person the CV never names."""
    known = context.vocabulary()
    for match in _GREETING.finditer(note.text):
        unknown = [token for token in words(match.group(1)) if token not in known]
        if unknown:
            return Violation(
                COVER_INVENTED_RECIPIENT,
                f"the greeting names someone the CV does not: {' '.join(unknown)}",
            )
    return None


def rule_vocabulary(note: CoverNoteDraft, context: CoverContext) -> Violation | None:
    """Rule 3: names, tools and certifications come from the CV or the job post."""
    known = context.vocabulary()
    unknown = [token for token in suspects(note.text) if not is_grounded(token, known)]
    if not unknown:
        return None
    return Violation(
        UNKNOWN_VOCABULARY,
        f"vocabulary absent from the CV: {', '.join(sorted(set(unknown)))}",
    )


def rule_claims(note: CoverNoteDraft, context: CoverContext) -> Violation | None:
    """Rule 4: the asserted indexes are confirmed matches with quotes in the CV."""
    if not note.asserted_requirement_indexes:
        return Violation(COVER_NO_CLAIMS, "the note asserts no confirmed match")
    known = {claim.index: claim for claim in context.strong}
    unknown = sorted({index for index in note.asserted_requirement_indexes if index not in known})
    if unknown:
        return Violation(COVER_INDEX_NOT_STRONG, f"indexes with no confirmed match: {unknown}")
    haystack = f"{context.guard.cv_text} {context.guard.skills_text}"
    for index in sorted(set(note.asserted_requirement_indexes)):
        if not contains_quote(haystack, known[index].quote):
            return Violation(
                COVER_QUOTE_NOT_IN_CV,
                f"the quote behind index {index} is not in the CV",
            )
    return None


def _mentions(body: str, keyword: str) -> bool:
    """Whole-word match inside already-normalised text; `ci/cd` works too."""
    needle = normalise(keyword)
    if not needle:
        return False
    pattern = rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])"
    return re.search(pattern, body) is not None


def rule_open(note: CoverNoteDraft, context: CoverContext) -> Violation | None:
    """Rule 5: a keyword from an unmet requirement cannot be asserted.

    A keyword the CV does support is allowed through: the note may only claim
    what the CV already proves, which is what "strong only" means here.
    """
    if not context.open_keywords:
        return None
    body = normalise(note.text)
    known = context.guard.vocabulary()
    hits = sorted(
        keyword
        for keyword in context.open_keywords
        if keyword not in known and _mentions(body, keyword)
    )
    if not hits:
        return None
    return Violation(
        COVER_OPEN_KEYWORD,
        f"keywords from unmet requirements: {', '.join(hits)}",
    )


CoverRule = Callable[[CoverNoteDraft, CoverContext], Violation | None]

#: Order is the contract: the first violation is the one that gets stored.
COVER_NOTE_RULES: tuple[CoverRule, ...] = (
    rule_length,
    rule_language,
    rule_recommendation,
    rule_banned,
    rule_numbers,
    rule_recipient,
    rule_vocabulary,
    rule_claims,
    rule_open,
)
