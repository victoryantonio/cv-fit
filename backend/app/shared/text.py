"""Text comparison helpers shared by the JD and CV pipelines.

Every quote check in this project compares *normalised* text: NFKC (so a fancy
quote in a PDF matches a straight one), collapsed whitespace and casefold. The
comparison never rewrites the stored text; only the check is lossy.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")


def normalise(text: str) -> str:
    """NFKC, collapse whitespace, casefold. For substring checks only."""
    folded = unicodedata.normalize("NFKC", text)
    return _WHITESPACE.sub(" ", folded).strip().casefold()


def contains_quote(haystack: str, quote: str) -> bool:
    """True when `quote` appears verbatim in `haystack` up to normalisation."""
    needle = normalise(quote)
    if not needle:
        return False
    return needle in normalise(haystack)


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())
