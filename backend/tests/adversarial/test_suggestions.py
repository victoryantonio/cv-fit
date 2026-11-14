"""PRD M4 on suggestions: an invented fact must never reach the packet.

Every case is the kind of rewrite a helpful model actually produces against this
CV: a percentage it did not measure, a cloud platform it never saw, a client name
borrowed from the JD, a certification, a promotion date, a team size, a buzzword.
The CV is a real one, so the passing control case proves the set is not simply
rejecting everything.

The cover-note half of M4 arrives with S8; until then this file covers S6.
"""

from __future__ import annotations

import pytest

from app.modules.analysis.enums import (
    SuggestionScope,
    SuggestionTarget,
    SuggestionType,
    Verdict,
)
from app.modules.analysis.guards import (
    BANNED_PHRASE,
    NUMBER_NOT_IN_CV,
    ORIGINAL_NOT_IN_CV,
    UNKNOWN_VOCABULARY,
    GuardContext,
    check_suggestion,
)
from app.modules.analysis.schemas import SuggestionOut

CV_TEXT = (
    "RINA PRATAMA\n"
    "Backend engineer with six years building payment and ledger services in Python.\n"
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes.\n"
    "Ran the ledger on PostgreSQL and wrote the SQL behind monthly reconciliation.\n"
)

RUNTIME_LINE = (
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes."
)
LEDGER_LINE = "Ran the ledger on PostgreSQL and wrote the SQL behind monthly reconciliation."

CONTEXT = GuardContext.build(cv_text=CV_TEXT, section_texts={"skills": "Python, PostgreSQL, SQL"})


def _suggestion(**overrides: object) -> SuggestionOut:
    payload: dict[str, object] = {
        "type": SuggestionType.REWORD,
        "scope": SuggestionScope.JOB_SPECIFIC,
        "target_section": SuggestionTarget.EXPERIENCE,
        "original_text": RUNTIME_LINE,
        "proposed_text": RUNTIME_LINE,
        "rationale": "Leads with the runtime cut.",
    }
    payload.update(overrides)
    return SuggestionOut.model_validate(payload)


CASES: list[tuple[str, dict[str, object], str | None]] = [
    (
        "faithful_rewrite",
        {"rationale": "Leads with the outcome the JD asks about."},
        None,
    ),
    (
        "invented_metric",
        {
            "proposed_text": f"{RUNTIME_LINE} Cut infrastructure spend by 32 percent.",
            "rationale": "Adds the cost angle.",
        },
        NUMBER_NOT_IN_CV,
    ),
    (
        "invented_date",
        {
            "proposed_text": "Promoted to Staff Engineer in 2021.",
            "original_text": RUNTIME_LINE,
            "rationale": "Shows progression.",
        },
        NUMBER_NOT_IN_CV,
    ),
    (
        "invented_team_size",
        {
            "proposed_text": f"{RUNTIME_LINE} Led a team of 12 engineers.",
            "rationale": "Shows scope.",
        },
        NUMBER_NOT_IN_CV,
    ),
    (
        "invented_tool",
        {
            "proposed_text": "Deployed the settlement worker to Kubernetes.",
            "rationale": "Mentions the platform named in the post.",
        },
        UNKNOWN_VOCABULARY,
    ),
    (
        "invented_client",
        {
            "proposed_text": "Delivered the ledger for Gojek.",
            "original_text": LEDGER_LINE,
            "rationale": "Names the kind of client the post wants.",
        },
        UNKNOWN_VOCABULARY,
    ),
    (
        "invented_certification",
        {
            "proposed_text": "AWS Certified Solutions Architect.",
            "original_text": None,
            "target_section": SuggestionTarget.SKILLS,
            "rationale": "Covers the cloud requirement.",
        },
        UNKNOWN_VOCABULARY,
    ),
    (
        "invented_original_lines",
        {
            "original_text": "Owned the payments platform roadmap.",
            "proposed_text": "Owned the payments platform roadmap for the ledger.",
            "rationale": "Reframes the role.",
        },
        ORIGINAL_NOT_IN_CV,
    ),
    (
        "empty_claim",
        {
            "proposed_text": "A passionate backend engineer.",
            "original_text": None,
            "target_section": SuggestionTarget.SUMMARY,
            "rationale": "Stronger opening.",
        },
        BANNED_PHRASE,
    ),
    (
        "significance_inflation",
        {
            "proposed_text": f"{RUNTIME_LINE} Spearheaded the migration.",
            "rationale": "Sounds more senior.",
        },
        BANNED_PHRASE,
    ),
]


@pytest.mark.parametrize(
    ("label", "overrides", "expected"),
    CASES,
    ids=[case[0] for case in CASES],
)
def test_the_adversarial_set_is_never_accepted(
    label: str, overrides: dict[str, object], expected: str | None
) -> None:
    result = check_suggestion(_suggestion(**overrides), CONTEXT)

    assert result.code == expected, label
    if expected is not None:
        assert result.ok is False


def test_the_guard_only_blocks_the_invented_field() -> None:
    """Control: the same CV and the same line, with the fabrication removed."""
    invented = _suggestion(proposed_text=f"{RUNTIME_LINE} Cut infrastructure spend by 32 percent.")
    cleaned = _suggestion(proposed_text=RUNTIME_LINE, rationale="Leads with the runtime cut.")

    assert check_suggestion(invented, CONTEXT).code == NUMBER_NOT_IN_CV
    assert check_suggestion(cleaned, CONTEXT).code is None


def test_a_gap_keyword_exemption_does_not_cover_a_verdict_of_gap() -> None:
    """The one exemption is scoped to requirements the CV already supports."""
    keyword = _suggestion(
        type=SuggestionType.ADD_KEYWORD,
        original_text=LEDGER_LINE,
        proposed_text="Kubernetes",
        rationale="Adds the missing platform.",
    )
    grounded = GuardContext.build(cv_text=CV_TEXT, verdict=Verdict.STRONG)
    open_item = GuardContext.build(cv_text=CV_TEXT, verdict=Verdict.GAP)

    assert check_suggestion(keyword, grounded).ok
    assert check_suggestion(keyword, open_item).code == UNKNOWN_VOCABULARY
