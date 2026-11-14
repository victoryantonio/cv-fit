"""When a run is allowed to block a merge, and when a comparison is meaningless.

The gate is the only thing standing between a quiet quality drop and a merge,
so each reason to block is pinned separately.
"""

from __future__ import annotations

import pytest

from app.eval_cli import _outcomes
from app.eval_metrics import (
    AGREEMENT_DROP_LIMIT,
    TARGETS,
    baseline_document,
    regressions,
)
from tests.unit.eval_helpers import metrics, payload


def test_a_run_inside_every_target_has_no_problems() -> None:
    assert regressions(metrics(), None) == []


@pytest.mark.parametrize("name", sorted(TARGETS))
def test_any_metric_below_target_blocks(name: str) -> None:
    problems = regressions(metrics(**{name: TARGETS[name] - 0.01}), None)

    assert any(problem.startswith(f"{name}:") for problem in problems)


def test_one_ungrounded_quote_blocks_the_run() -> None:
    problems = regressions(metrics(ungrounded=1), None)

    assert any(problem.startswith("ungrounded:") for problem in problems)


def test_one_unsupported_fact_blocks_the_run() -> None:
    problems = regressions(metrics(unsupported=1), None)

    assert any(problem.startswith("unsupported:") for problem in problems)


def test_a_missing_baseline_is_a_first_run_not_a_failure() -> None:
    assert regressions(metrics(), {"metrics": {}}) == []


def test_a_small_agreement_drop_is_tolerated() -> None:
    drop = AGREEMENT_DROP_LIMIT / 100 / 2
    baseline = {"metrics": {"agreement": 0.9 + drop}}

    assert regressions(metrics(agreement=0.9), baseline) == []


def test_a_large_agreement_drop_blocks_the_run() -> None:
    baseline = {"metrics": {"agreement": 0.95}, "cases": 1}

    problems = regressions(metrics(agreement=0.90), baseline, case_ids=("jd-01",))

    assert any("agreement dropped" in problem for problem in problems)


def test_an_improvement_is_never_a_regression() -> None:
    baseline = {"metrics": {"agreement": 0.85}}

    assert regressions(metrics(agreement=0.95), baseline) == []


def test_a_quote_spread_over_a_line_break_is_grounded() -> None:
    """The CV is a PDF extraction, so containment is judged after normalisation.

    A bullet that wraps in the PDF reads as one space in the quote and as a
    newline in the extracted text. Comparing raw strings called that invented
    evidence, which is a measurement bug that would fail a correct pipeline.
    """
    cv_text = (
        "RINA\n\u25cf Built dashboards \u2014 na\u00efve charts for the\n"
        "board\n\u25cf Cut latency 40%"
    )
    document = payload(
        [("req-1", "Build dashboards")],
        [
            {
                "requirement_id": "req-1",
                "verdict": "strong",
                "votes": {"strong": 3},
                "evidence_quote": "Built dashboards \u2014 na\u00efve charts for the board",
            }
        ],
    )

    outcomes, _ = _outcomes(document, [("Build dashboards", "strong")], cv_text)

    assert outcomes[0].grounded is True


def test_a_quote_that_joins_two_bullets_is_still_ungrounded() -> None:
    """Whitespace normalisation must not glue separate bullets into evidence."""
    cv_text = "RINA\n\u25cf Built dashboards\n\u25cf Cut latency 40%"
    document = payload(
        [("req-1", "Build dashboards")],
        [
            {
                "requirement_id": "req-1",
                "verdict": "strong",
                "votes": {"strong": 3},
                "evidence_quote": "Built dashboards Cut latency 40%",
            }
        ],
    )

    outcomes, _ = _outcomes(document, [("Build dashboards", "strong")], cv_text)

    assert outcomes[0].grounded is False


def test_a_quote_the_cv_does_not_contain_is_still_ungrounded() -> None:
    """Normalising widens containment by whitespace and width, not by wording."""
    cv_text = "RINA\n\u25cf Built dashboards"
    document = payload(
        [("req-1", "Build dashboards")],
        [
            {
                "requirement_id": "req-1",
                "verdict": "strong",
                "votes": {"strong": 3},
                "evidence_quote": "Led the company-wide Kubernetes migration",
            }
        ],
    )

    outcomes, _ = _outcomes(document, [("Build dashboards", "strong")], cv_text)

    assert outcomes[0].grounded is False


def test_a_baseline_from_a_different_case_set_is_not_compared() -> None:
    """A bigger, harder set moves the average with no change in quality."""
    baseline = {
        "metrics": {"agreement": 0.95},
        "case_ids": ["example-noisy", "example-payments"],
    }

    problems = regressions(metrics(agreement=0.79), baseline, case_ids=("jd-01", "jd-02"))

    assert problems == []


def test_a_baseline_on_the_same_case_set_still_blocks_a_drop() -> None:
    baseline = {"metrics": {"agreement": 0.95}, "case_ids": ["jd-01", "jd-02"]}

    problems = regressions(metrics(agreement=0.79), baseline, case_ids=("jd-01", "jd-02"))

    assert any("agreement dropped" in problem for problem in problems)


def test_the_shipped_metrics_only_baseline_is_compared_on_its_case_count() -> None:
    """`eval/baseline.json` cannot carry case ids, so it records how many it measured."""
    baseline = {"cases": 2, "metrics": {"agreement": 1.0}}

    assert regressions(metrics(agreement=0.8), baseline, case_ids=("a", "b", "c")) == []
    assert regressions(metrics(agreement=0.8), baseline, case_ids=("a", "b")) != []


def test_a_baseline_with_no_case_evidence_is_not_compared() -> None:
    """Silently passing is worse than not comparing, but a blind drop is worse still."""
    baseline = {"metrics": {"agreement": 1.0}}

    problems = regressions(metrics(agreement=0.90), baseline, case_ids=("a", "b"))

    assert problems == []


def test_a_baseline_drops_the_case_detail() -> None:
    """The report holds gold text and CV quotes; the baseline must hold neither."""
    report = {
        "generated_at": "2026-11-13T00:00:00+00:00",
        "model": "deepseek-v4-flash",
        "prompt_bundle": "abc123",
        "match_runs": 3,
        "case_ids": ["jd-01", "jd-02"],
        "metrics": {"agreement": 0.9},
        "targets": {"agreement": 0.75},
        "problems": [],
        "passed": True,
        "cases": [
            {
                "case_id": "jd-01",
                "requirements": [
                    {"gold_text": "5 years of Python", "evidence_quote": "Python since 2019"}
                ],
            }
        ],
    }

    document = baseline_document(report)

    assert "cases" not in document
    assert "problems" not in document
    assert document["case_ids"] == ["jd-01", "jd-02"]
    assert document["metrics"] == {"agreement": 0.9}
