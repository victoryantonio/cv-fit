"""One matcher script: five requirements, three judgment runs each.

Two requirements are strong with a verbatim CV quote; the other three are not.
The quoted lines are the only facts a cover note is allowed to assert, so the
same set drives the S6 and S8 tests.
"""

from __future__ import annotations

from typing import Any

CV_TEXT = (
    "RINA PRATAMA\n"
    "Backend engineer with six years building payment and ledger services in Python.\n"
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes.\n"
    "Ran the ledger on PostgreSQL and wrote the SQL behind monthly reconciliation.\n"
    "Reviewed merge requests and paired with two junior engineers each week.\n"
)

QUOTE_PYTHON = (
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes."
)
QUOTE_SQL = "Ran the ledger on PostgreSQL and wrote the SQL behind monthly reconciliation."
LINE_MERGE = "Reviewed merge requests and paired with two junior engineers each week."

STRONG_PYTHON: dict[str, Any] = {
    "verdict": "strong",
    "evidence_quote": QUOTE_PYTHON,
    "rationale": "Names the work, the language and the outcome.",
    "missing": [],
}
STRONG_SQL: dict[str, Any] = {
    "verdict": "strong",
    "evidence_quote": QUOTE_SQL,
    "rationale": "Names the database and the query work.",
    "missing": [],
}
GAP_AWS: dict[str, Any] = {
    "verdict": "gap",
    "evidence_quote": None,
    "rationale": "The CV never mentions a cloud provider.",
    "missing": ["AWS", "ECS", "Kubernetes"],
}
PARTIAL_MENTOR: dict[str, Any] = {
    "verdict": "partial",
    "evidence_quote": LINE_MERGE,
    "rationale": "Shows review and pairing, not formal mentoring of mid-level engineers.",
    "missing": ["mid-level engineers"],
}
PARTIAL_ENGLISH: dict[str, Any] = {
    "verdict": "partial",
    "evidence_quote": "Backend engineer with six years building payment and ledger services",
    "rationale": "Shows written work, not a language test.",
    "missing": ["written English"],
}

MATCH_SCRIPT: list[dict[str, Any]] = [
    STRONG_PYTHON,
    STRONG_SQL,
    GAP_AWS,
    PARTIAL_MENTOR,
    PARTIAL_ENGLISH,
]

#: Every requirement uncovered: nothing may be asserted, so no note is written.
ALL_GAP: list[dict[str, Any]] = [
    {
        "verdict": "gap",
        "evidence_quote": None,
        "rationale": "No evidence in the CV.",
        "missing": ["everything"],
    }
] * len(MATCH_SCRIPT)
