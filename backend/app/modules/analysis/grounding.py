"""S3: a verdict only counts if its quote is really in the CV.

The prompt asks for a verbatim quote and the schema refuses credit without one,
but neither is proof: the model can still paraphrase or invent. This check is
the only authority. A quote that is not verbatim is cut back to the longest
verbatim sentence it contains; if no sentence survives, the credit is a gap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from app.modules.analysis.enums import Verdict
from app.shared.text import contains_quote

UNGROUNDED_FLAG: Final = "ungrounded_evidence"
QUOTE_TRIMMED_FLAG: Final = "quote_trimmed"

_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
MIN_FRAGMENT_WORDS: Final = 2

CREDITED: Final[frozenset[str]] = frozenset({Verdict.STRONG, Verdict.PARTIAL})


@dataclass(frozen=True, slots=True)
class Grounded:
    verdict: str
    evidence_quote: str | None = None
    rationale: str = ""
    flags: tuple[str, ...] = ()


def _counts_as_evidence(cv_text: str, text: str) -> bool:
    """Verbatim, and long enough that a stray word cannot carry a verdict."""
    return len(text.split()) >= MIN_FRAGMENT_WORDS and contains_quote(cv_text, text)


def _verbatim_fragment(cv_text: str, quote: str) -> str | None:
    """The longest sentence of `quote` that really appears in the CV.

    A model that copies two separate lines into one quote is not inventing
    evidence, only joining it, so the joined string is still not verbatim while
    real CV text sits inside it. Crediting the join would store a quote the CV
    does not contain; discarding it would report a gap where the CV answers.
    Keeping the piece that is verbatim, and flagging the trim, is the honest
    middle.
    """
    best = ""
    for piece in _SENTENCE.split(quote):
        candidate = piece.strip()
        if len(candidate) > len(best) and _counts_as_evidence(cv_text, candidate):
            best = candidate
    return best or None


def ground(
    *,
    verdict: str,
    evidence_quote: str | None,
    cv_text: str,
    rationale: str = "",
) -> Grounded:
    """Downgrade to gap unless verbatim evidence from the CV survives."""
    if verdict not in CREDITED:
        return Grounded(verdict=Verdict.GAP)
    quote = (evidence_quote or "").strip()
    if not quote:
        return Grounded(verdict=Verdict.GAP)
    if not _counts_as_evidence(cv_text, quote):
        fragment = _verbatim_fragment(cv_text, quote)
        if fragment is None:
            return Grounded(verdict=Verdict.GAP, flags=(UNGROUNDED_FLAG,))
        return Grounded(
            verdict=verdict,
            evidence_quote=fragment,
            rationale=rationale,
            flags=(QUOTE_TRIMMED_FLAG,),
        )
    return Grounded(verdict=verdict, evidence_quote=quote, rationale=rationale)
