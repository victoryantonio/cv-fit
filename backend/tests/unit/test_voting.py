"""S4: majority vote, and a tie that never resolves upward."""

from __future__ import annotations

from app.modules.analysis.voting import STABILITY_THRESHOLD, UNSTABLE_FLAG, tally


def test_unanimous_runs_are_stable() -> None:
    vote = tally(["strong", "strong", "strong"])

    assert vote.verdict == "strong"
    assert vote.votes == {"strong": 3}
    assert vote.agreement == 1.0
    assert vote.flags == ()
    assert vote.unstable is False


def test_two_of_three_is_a_majority_and_is_not_unstable() -> None:
    """0.6666... must round up to 0.67, otherwise a real majority looks unstable."""
    vote = tally(["strong", "strong", "partial"])

    assert vote.verdict == "strong"
    assert vote.agreement == 0.67
    assert vote.agreement >= STABILITY_THRESHOLD
    assert vote.unstable is False


def test_a_minority_never_wins() -> None:
    vote = tally(["gap", "gap", "strong"])

    assert vote.verdict == "gap"
    assert vote.agreement == 0.67


def test_three_way_tie_falls_back_to_the_lowest_verdict() -> None:
    vote = tally(["strong", "partial", "gap"])

    assert vote.verdict == "gap"
    assert vote.agreement == 0.33
    assert vote.flags == (UNSTABLE_FLAG,)
    assert vote.unstable is True


def test_tie_between_two_verdicts_takes_the_conservative_one() -> None:
    assert tally(["strong", "partial"]).verdict == "partial"
    assert tally(["partial", "gap"]).verdict == "gap"
    assert tally(["strong", "gap"]).verdict == "gap"


def test_counts_are_sorted_for_determinism() -> None:
    vote = tally(["strong", "gap", "gap"])

    assert list(vote.votes) == ["gap", "strong"]


def test_no_runs_is_a_gap_and_unstable() -> None:
    vote = tally([])

    assert vote.verdict == "gap"
    assert vote.votes == {}
    assert vote.agreement == 0.0
    assert vote.unstable is True
