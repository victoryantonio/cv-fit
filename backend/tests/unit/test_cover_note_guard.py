"""S8 in isolation: one passing note, then one rejection per rule.

The guard is the last thing between a helpful sentence and a claim the CV cannot
back, so each rule gets a case that trips only that rule, and the control case
proves the rule set is not simply refusing everything.
"""

from __future__ import annotations

import pytest

from app.modules.analysis.guards import (
    BANNED_PHRASE,
    COVER_INDEX_NOT_STRONG,
    COVER_INVENTED_RECIPIENT,
    COVER_LENGTH_OUT_OF_RANGE,
    COVER_NO_CLAIMS,
    COVER_NOT_ENGLISH,
    COVER_OPEN_KEYWORD,
    COVER_QUOTE_NOT_IN_CV,
    COVER_RECOMMENDATION,
    NUMBER_NOT_IN_CV,
    UNKNOWN_VOCABULARY,
    CoverClaim,
    CoverContext,
    GuardContext,
    check_cover_note,
)
from app.modules.analysis.schemas import CoverNoteDraft
from tests.fixtures.cover_notes import COVER_TEXT

CV_TEXT = (
    "RINA PRATAMA\n"
    "Backend engineer with six years building payment and ledger services in Python.\n"
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes.\n"
    "Ran the ledger on PostgreSQL and wrote the SQL behind monthly reconciliation.\n"
    "Reviewed merge requests and paired with two junior engineers each week.\n"
)

RUNTIME_LINE = (
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes."
)
LEDGER_LINE = "Ran the ledger on PostgreSQL and wrote the SQL behind monthly reconciliation."

INDONESIAN = (
    "Saya menulis untuk melamar posisi backend engineer di Acme Payments. "
    "Selama enam tahun saya mengerjakan layanan pembayaran dan buku besar dengan Python, "
    "membangun ulang proses penyelesaian dan memotong waktu akhir hari. "
    "Saya juga mengelola basis data dan menulis kueri untuk rekonsiliasi bulanan. "
    "Saya ingin membawa pengalaman itu ke tim Anda dan mendiskusikan pekerjaan rekonsiliasi "
    "yang saya lakukan bersama engineer lain setiap minggu. Terima kasih atas waktunya."
)


def _context(**overrides: object) -> CoverContext:
    payload: dict[str, object] = {
        "guard": GuardContext.build(
            cv_text=CV_TEXT, section_texts={"skills": "Python, PostgreSQL, SQL"}
        ),
        "strong": (
            CoverClaim(0, "Five years of Python", RUNTIME_LINE),
            CoverClaim(1, "Strong SQL and PostgreSQL", LEDGER_LINE),
        ),
        "open_keywords": frozenset({"kubernetes", "terraform"}),
        "reserved": frozenset({"acme", "payments", "senior", "backend", "engineer"}),
        "min_words": 60,
        "max_words": 150,
    }
    payload.update(overrides)
    return CoverContext(**payload)  # type: ignore[arg-type]


CONTEXT = _context()


def _note(text: str, asserted: list[int] | None = None) -> CoverNoteDraft:
    return CoverNoteDraft(
        text=text,
        asserted_requirement_indexes=[0] if asserted is None else asserted,
    )


CASES: list[tuple[str, str, list[int], str | None]] = [
    ("faithful_note", COVER_TEXT, [0, 1], None),
    (
        "too_short",
        "I rebuilt the settlement worker in Python and would like to talk about the role.",
        [0],
        COVER_LENGTH_OUT_OF_RANGE,
    ),
    ("not_english", INDONESIAN, [0], COVER_NOT_ENGLISH),
    (
        "recommendation_language",
        f"{COVER_TEXT} You should apply today.",
        [0],
        COVER_RECOMMENDATION,
    ),
    (
        "probability_language",
        f"{COVER_TEXT} There is a good chance of an interview.",
        [0],
        COVER_RECOMMENDATION,
    ),
    ("empty_claim", f"{COVER_TEXT} I am a passionate team player.", [0], BANNED_PHRASE),
    ("invented_metric", f"{COVER_TEXT} I cut costs by 32 percent.", [0], NUMBER_NOT_IN_CV),
    (
        "invented_tool",
        f"{COVER_TEXT} I deployed the worker on Kubernetes.",
        [0],
        UNKNOWN_VOCABULARY,
    ),
    (
        "unnamed_recipient",
        f"Dear Nadia,\n{COVER_TEXT}",
        [0],
        COVER_INVENTED_RECIPIENT,
    ),
    ("no_claims", COVER_TEXT, [], COVER_NO_CLAIMS),
    ("index_not_strong", COVER_TEXT, [7], COVER_INDEX_NOT_STRONG),
    (
        "open_requirement",
        f"{COVER_TEXT} I also leaned on terraform for the rollout.",
        [0],
        COVER_OPEN_KEYWORD,
    ),
]


@pytest.mark.parametrize(
    ("label", "text", "asserted", "expected"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_each_rule_rejects_its_own_case(
    label: str, text: str, asserted: list[int], expected: str | None
) -> None:
    result = check_cover_note(_note(text, asserted), CONTEXT)

    assert result.code == expected, label
    if expected is not None:
        assert result.status == f"rejected_{expected}"


def test_a_quote_the_cv_does_not_contain_is_rejected() -> None:
    """A strong verdict with invented evidence cannot carry a claim."""
    context = _context(
        strong=(CoverClaim(0, "Kubernetes at scale", "Ran the fleet on Kubernetes"),)
    )

    result = check_cover_note(_note(COVER_TEXT), context)

    assert result.code == COVER_QUOTE_NOT_IN_CV


def test_a_role_greeting_needs_no_cv_source() -> None:
    """`Dear hiring manager` names a slot, so it is allowed through."""
    result = check_cover_note(_note(f"Dear hiring manager,\n{COVER_TEXT}"), CONTEXT)

    assert result.ok is True
