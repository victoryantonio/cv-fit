"""Scripted cover notes. Every string here is checked by the guard in code.

`COVER_OK` uses only words the fixture CV already contains (plus the role and the
company, which the guard lets a note name), so it passes every S8 rule as long as
the requirements it asserts are the strong ones.
"""

from __future__ import annotations

from typing import Any

COVER_TEXT = (
    "I am writing about the senior backend engineer role at Acme Payments. "
    "My last six years went into payment and ledger services in Python, where I "
    "rebuilt the settlement worker and cut end-of-day runtime from forty minutes to six. "
    "I ran the ledger on PostgreSQL and wrote the queries behind the monthly reconciliation, "
    "and that settlement rewrite is the work I would bring to your team first. "
    "I would welcome a conversation about the reconciliation query and the pairing "
    "I did with junior engineers."
)

COVER_OK: dict[str, Any] = {
    "text": COVER_TEXT,
    "asserted_requirement_indexes": [0, 1],
}

#: Same note with one claim too many: index 2 is a gap in every fixture.
COVER_UNKNOWN_INDEX: dict[str, Any] = {
    "text": COVER_TEXT,
    "asserted_requirement_indexes": [0, 2],
}


def with_text(text: str, asserted: list[int] | None = None) -> dict[str, Any]:
    return {"text": text, "asserted_requirement_indexes": asserted or [0]}
