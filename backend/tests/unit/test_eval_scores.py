"""How a run's per-requirement verdicts are turned into numbers.

A refusal case has no requirements, so it must not count as a miss. These tests
pin that arithmetic without touching a model.
"""

from __future__ import annotations

from app.eval_metrics import Outcome, regressions, summarize
from tests.unit.eval_helpers import case, outcome


def test_a_perfect_run_scores_one() -> None:
    metrics = summarize([case(outcomes=[outcome("strong", "strong")])], 3)

    assert metrics["agreement"] == 1.0
    assert metrics["stability"] == 1.0
    assert metrics["structuring_accuracy"] == 1.0
    assert metrics["ungrounded"] == 0
    assert metrics["cases"] == 1


def test_disagreement_is_counted_per_requirement() -> None:
    metrics = summarize(
        [
            case(
                outcomes=[
                    outcome("strong", "strong"),
                    outcome("gap", "strong"),
                    outcome("partial", "gap"),
                    outcome("partial", "partial"),
                ]
            )
        ],
        3,
    )

    assert metrics["agreement"] == 0.5
    assert metrics["requirements"] == 4


def test_a_split_vote_is_unstable_and_a_unanimous_one_is_not() -> None:
    metrics = summarize(
        [
            case(
                outcomes=[
                    outcome("strong", "strong", votes={"strong": 3}),
                    outcome("strong", "strong", votes={"strong": 2, "partial": 1}),
                ]
            )
        ],
        3,
    )

    assert metrics["stability"] == 0.5


def test_a_requirement_the_extractor_missed_is_reported_as_absent() -> None:
    missing = Outcome(gold_text="Kubernetes", gold_verdict="strong")

    assert missing.verdict is None
    assert missing.agree is False
    assert missing.is_stable(3) is True


def test_structuring_reads_extracted_over_expected() -> None:
    metrics = summarize(
        [
            case(case_id="a", extracted_total=4, extracted_matched=3),
            case(case_id="b", extracted_total=6, extracted_matched=6),
        ],
        3,
    )

    assert metrics["structuring_accuracy"] == 0.9


def test_ungrounded_and_unsupported_are_summed_not_averaged() -> None:
    metrics = summarize(
        [
            case(case_id="a", unsupported=2),
            case(case_id="b", unsupported=1),
        ],
        3,
    )

    assert metrics["unsupported"] == 3


def test_an_empty_run_does_not_divide_by_zero() -> None:
    metrics = summarize([], 3)

    assert metrics["agreement"] == 0.0
    assert metrics["stability"] == 0.0
    assert metrics["structuring_accuracy"] == 0.0
    assert metrics["latency_p50_ms"] == 0


def test_latency_percentiles_come_from_the_cases() -> None:
    metrics = summarize(
        [
            case(case_id=str(index), latency_ms=latency)
            for index, latency in enumerate([10, 20, 30])
        ],
        3,
    )

    assert metrics["latency_p50_ms"] == 20
    assert metrics["latency_p95_ms"] == 30


def test_a_refusal_case_does_not_dilute_the_judgment_metrics() -> None:
    """A page that must be refused has no requirements; it cannot count as a miss."""
    metrics = summarize(
        [
            case(case_id="pair", outcomes=[outcome("strong", "strong")], latency_ms=800),
            case(
                case_id="nav",
                outcomes=[],
                extracted_total=0,
                extracted_matched=0,
                tokens=0,
                latency_ms=0,
                expect="JD_NOT_FOUND",
                actual="JD_NOT_FOUND",
            ),
        ],
        3,
    )

    assert metrics["agreement"] == 1.0
    assert metrics["structuring_accuracy"] == 1.0
    assert metrics["latency_p50_ms"] == 800
    assert metrics["cases"] == 2
    assert metrics["analysed_cases"] == 1
    assert metrics["refusals"] == 1
    assert metrics["refusals_correct"] == 1


def test_a_subset_of_only_refusals_measures_no_judgment_and_blocks_nothing() -> None:
    metrics = summarize(
        [
            case(
                case_id="nav",
                outcomes=[],
                extracted_total=0,
                extracted_matched=0,
                expect="JD_NOT_FOUND",
                actual="JD_NOT_FOUND",
            )
        ],
        3,
    )

    assert regressions(metrics, None) == []


def test_the_wrong_refusal_code_is_a_miss() -> None:
    """Refusing for the wrong reason means the page was read the wrong way."""
    result = case(case_id="list", expect="JD_MULTIPLE_JOBS", actual="JD_NOT_FOUND")

    assert result.satisfied is False


def test_the_expected_refusal_code_is_a_pass() -> None:
    result = case(case_id="list", expect="JD_MULTIPLE_JOBS", actual="JD_MULTIPLE_JOBS")

    assert result.satisfied is True


def test_a_pair_that_ran_normally_is_satisfied() -> None:
    assert case().satisfied is True
