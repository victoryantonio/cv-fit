"""S6: every rule fires on the rewrite it was written for, and only then.

One pass case and one fail case per rule. The rules are ordered, so a case that
breaks two rules is asserted against the first one; that order is the contract.
"""

from __future__ import annotations

from app.modules.analysis.enums import (
    GuardStatus,
    SuggestionScope,
    SuggestionTarget,
    SuggestionType,
    Verdict,
)
from app.modules.analysis.guards import (
    BANNED_PHRASE,
    GAP_NOTE_HAS_REWRITE,
    NUMBER_NOT_IN_CV,
    ORIGINAL_NOT_IN_CV,
    UNKNOWN_VOCABULARY,
    GuardContext,
    check_suggestion,
    rejected,
)
from app.modules.analysis.schemas import SuggestionOut

CV_TEXT = (
    "RINA PRATAMA\n"
    "Backend engineer with six years building payment and ledger services in Python.\n"
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes.\n"
    "Ran the ledger on PostgreSQL and wrote the SQL behind monthly reconciliation.\n"
    "Set up CI and CD for the settlement service.\n"
)

SKILLS = "Python, PostgreSQL, SQL"

LINE_PYTHON = (
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes."
)


def _context(verdict: Verdict | None = None) -> GuardContext:
    return GuardContext.build(cv_text=CV_TEXT, section_texts={"skills": SKILLS}, verdict=verdict)


def _suggestion(**overrides: object) -> SuggestionOut:
    payload: dict[str, object] = {
        "type": SuggestionType.REWORD,
        "scope": SuggestionScope.JOB_SPECIFIC,
        "target_section": SuggestionTarget.EXPERIENCE,
        "original_text": LINE_PYTHON,
        "proposed_text": LINE_PYTHON,
        "rationale": "Leads with the outcome.",
    }
    payload.update(overrides)
    return SuggestionOut.model_validate(payload)


def test_a_faithful_rewrite_passes() -> None:
    result = check_suggestion(_suggestion(), _context())

    assert result.ok is True
    assert result.status == GuardStatus.PASS
    assert result.code is None


def test_original_text_must_exist_in_the_cv() -> None:
    passing = _suggestion(
        original_text="Ran the ledger on PostgreSQL",
        proposed_text="Ran the ledger on PostgreSQL",
    )
    failing = _suggestion(
        original_text="Owned the payments platform at a fintech",
        proposed_text="Owned the payments platform at a fintech",
    )

    assert check_suggestion(passing, _context()).code is None
    violation = check_suggestion(failing, _context())

    assert violation.code == ORIGINAL_NOT_IN_CV
    assert violation.status == rejected(ORIGINAL_NOT_IN_CV)


def test_every_number_must_already_be_in_the_cv() -> None:
    passing = _suggestion(proposed_text=f"{LINE_PYTHON} Cut the next release by 40 to 6 minutes.")
    failing = _suggestion(proposed_text=f"{LINE_PYTHON} Cut runtime by 87 percent.")

    assert check_suggestion(passing, _context()).code is None
    violation = check_suggestion(failing, _context())

    assert violation.code == NUMBER_NOT_IN_CV
    assert violation.detail is not None
    assert "87" in violation.detail


def test_invented_tool_is_rejected() -> None:
    """`Kubernetes` is capitalised, so it reads as a tool the CV must support."""
    passing = _suggestion(proposed_text="Moved the settlement worker onto PostgreSQL.")
    failing = _suggestion(proposed_text="Moved the settlement worker onto Kubernetes.")

    assert check_suggestion(passing, _context()).code is None
    violation = check_suggestion(failing, _context())

    assert violation.code == UNKNOWN_VOCABULARY
    assert violation.detail is not None
    assert "kubernetes" in violation.detail


def test_invented_certification_is_rejected() -> None:
    failing = _suggestion(proposed_text="Holds the AWS certification for data analytics.")

    violation = check_suggestion(failing, _context())

    assert violation.code == UNKNOWN_VOCABULARY


def test_invented_employer_is_rejected() -> None:
    """An acronym is treated as a factual claim wherever it sits in the line."""
    failing = _suggestion(proposed_text="Built the ledger at Stripe.")

    violation = check_suggestion(failing, _context())

    assert violation.code == UNKNOWN_VOCABULARY


def test_banned_phrase_is_rejected_in_the_rationale_too() -> None:
    """Inflation is not made acceptable by moving it out of the rewrite."""
    passing = _suggestion(rationale="Names the runtime cut.")
    failing = _suggestion(rationale="A results-driven rewrite of the same line.")

    assert check_suggestion(passing, _context()).code is None
    violation = check_suggestion(failing, _context())

    assert violation.code == BANNED_PHRASE
    assert violation.detail is not None
    assert "results-driven" in violation.detail


def test_gap_note_must_not_carry_rewrite_text() -> None:
    """The schema forbids a gap_note with text; the rule is the backstop for rows."""
    note = SuggestionOut.model_construct(
        type=SuggestionType.GAP_NOTE,
        scope=SuggestionScope.GENERAL,
        target_section=SuggestionTarget.OTHER,
        original_text=None,
        proposed_text="Led the AWS migration.",
        rationale="No CV evidence for: cloud deployment",
    )
    clean = _suggestion(
        type=SuggestionType.GAP_NOTE,
        scope=SuggestionScope.GENERAL,
        target_section=SuggestionTarget.OTHER,
        original_text=None,
        proposed_text=None,
        rationale="No CV evidence for: cloud deployment",
    )

    assert check_suggestion(clean, _context()).code is None
    violation = check_suggestion(note, _context())

    assert violation.code == GAP_NOTE_HAS_REWRITE


def test_add_keyword_is_checked_like_any_other_claim_when_it_names_a_tool() -> None:
    """The exemption is for a requirement the CV already covers, not for new facts."""
    keyword = _suggestion(
        type=SuggestionType.ADD_KEYWORD,
        original_text="Ran the ledger on PostgreSQL",
        proposed_text="AWS",
        rationale="The requirement is covered by the ledger line.",
    )

    assert check_suggestion(keyword, _context(Verdict.STRONG)).code is None
    assert check_suggestion(keyword, _context(Verdict.PARTIAL)).code is None
    rejected_for_gap = check_suggestion(keyword, _context(Verdict.GAP))
    assert rejected_for_gap.code == UNKNOWN_VOCABULARY


def test_a_one_word_proposal_is_still_a_claim() -> None:
    """`Terraform` on its own has no sentence to open, so the capital names a tool."""
    failing = _suggestion(
        type=SuggestionType.ADD_KEYWORD,
        original_text="Ran the ledger on PostgreSQL",
        proposed_text="Terraform",
        rationale="Adds the tool the requirement names.",
    )

    assert check_suggestion(failing, _context(Verdict.GAP)).code == UNKNOWN_VOCABULARY


def test_multi_word_tool_counts_as_known_when_the_cv_has_both_parts() -> None:
    proposal = _suggestion(
        type=SuggestionType.ADD_KEYWORD,
        original_text="Set up CI and CD for the settlement service.",
        proposed_text="CI/CD",
    )

    assert check_suggestion(proposal, _context(Verdict.GAP)).code is None


def test_rejected_status_is_the_rule_code() -> None:
    assert rejected(NUMBER_NOT_IN_CV) == "rejected_numbers_not_in_cv"
