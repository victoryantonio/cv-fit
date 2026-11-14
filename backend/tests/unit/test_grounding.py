"""S3: credit survives only when the quote is really in the CV."""

from __future__ import annotations

from app.modules.analysis.grounding import QUOTE_TRIMMED_FLAG, UNGROUNDED_FLAG, ground

CV_TEXT = (
    "RINA PRATAMA\n"
    "EXPERIENCE\n"
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes.\n"
    "Ran PostgreSQL queries against the ledger for monthly reconciliation.\n"
)

# The two quoted sentences are three lines apart, so joining them is not verbatim.
SPLICED_CV = (
    "RINA PRATAMA\n"
    "EXPERIENCE\n"
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes.\n"
    "Reviewed the monthly close with finance.\n"
    "Ran PostgreSQL queries against the ledger for monthly reconciliation.\n"
)


def test_verbatim_quote_keeps_the_verdict() -> None:
    result = ground(
        verdict="strong",
        evidence_quote="Ran PostgreSQL queries against the ledger",
        cv_text=CV_TEXT,
        rationale="Names the database and the work.",
    )

    assert result.verdict == "strong"
    assert result.evidence_quote == "Ran PostgreSQL queries against the ledger"
    assert result.rationale == "Names the database and the work."
    assert result.flags == ()


def test_paraphrase_is_downgraded_and_flagged() -> None:
    """The model rewrote "Python" as a sentence that is not in the file."""
    result = ground(
        verdict="strong",
        evidence_quote="Six years of professional Python experience",
        cv_text=CV_TEXT,
    )

    assert result.verdict == "gap"
    assert result.evidence_quote is None
    assert result.flags == (UNGROUNDED_FLAG,)


def test_credit_without_a_quote_is_a_gap() -> None:
    for quote in (None, "", "   "):
        result = ground(verdict="partial", evidence_quote=quote, cv_text=CV_TEXT)

        assert result.verdict == "gap"
        assert result.evidence_quote is None
        assert result.flags == ()


def test_gap_keeps_its_quote_out_of_the_record() -> None:
    result = ground(
        verdict="gap",
        evidence_quote="Ran PostgreSQL queries against the ledger",
        cv_text=CV_TEXT,
    )

    assert result.verdict == "gap"
    assert result.evidence_quote is None


def test_a_quote_spliced_from_two_lines_keeps_its_verdict() -> None:
    """The model joined two real lines. The join is not verbatim, the text is."""
    result = ground(
        verdict="strong",
        evidence_quote=(
            "Rebuilt the settlement worker in Python and cut end-of-day runtime "
            "from 40 to 6 minutes. Ran PostgreSQL queries against the ledger for "
            "monthly reconciliation."
        ),
        cv_text=SPLICED_CV,
    )

    assert result.verdict == "strong"
    assert result.flags == (QUOTE_TRIMMED_FLAG,)
    assert result.evidence_quote in SPLICED_CV


def test_the_surviving_fragment_is_the_longest_verbatim_one() -> None:
    result = ground(
        verdict="partial",
        evidence_quote=(
            "Taught a Python course. Ran PostgreSQL queries against the ledger for "
            "monthly reconciliation."
        ),
        cv_text=SPLICED_CV,
    )

    assert result.evidence_quote == (
        "Ran PostgreSQL queries against the ledger for monthly reconciliation."
    )


def test_a_splice_with_no_verbatim_sentence_is_still_a_gap() -> None:
    result = ground(
        verdict="strong",
        evidence_quote="Led the ledger rewrite. Owned the settlement service.",
        cv_text=SPLICED_CV,
    )

    assert result.verdict == "gap"
    assert result.flags == (UNGROUNDED_FLAG,)


def test_a_fragment_too_short_to_be_evidence_is_still_a_gap() -> None:
    """A stray word that happens to appear in the CV must not rescue a verdict."""
    result = ground(verdict="strong", evidence_quote="ledger", cv_text=CV_TEXT)

    assert result.verdict == "gap"
    assert result.flags == (UNGROUNDED_FLAG,)
