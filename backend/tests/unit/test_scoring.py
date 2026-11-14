"""Coverage math: weights, verdict values, labels. Pure functions in, numbers out."""

from __future__ import annotations

from app.modules.analysis.scoring import (
    RequirementResult,
    fit_label,
    score,
    value_of,
    weight_of,
)


def _result(
    requirement_id: str,
    *,
    importance: str = "weight",
    verdict: str = "gap",
    position: int = 1,
) -> RequirementResult:
    return RequirementResult(
        requirement_id=requirement_id,
        position=position,
        text=f"Requirement {requirement_id}",
        importance=importance,
        verdict=verdict,
    )


def test_weights_and_values_are_the_documented_ones() -> None:
    assert weight_of("knockout") == 3
    assert weight_of("weight") == 3
    assert weight_of("nice") == 1
    assert value_of("strong") == 1.0
    assert value_of("partial") == 0.5
    assert value_of("gap") == 0.0
    assert value_of("unknown") == 0.0


def test_mixed_coverage_is_weighted_by_importance() -> None:
    """3 strong + 3 partial + 1 gap over 7 total weight is 4.5 points, so 64%."""
    results = [
        _result("r1", importance="knockout", verdict="strong"),
        _result("r2", importance="weight", verdict="partial"),
        _result("r3", importance="nice", verdict="gap"),
    ]

    scored = score(results)

    assert (scored.points, scored.total_weight) == (4.5, 7)
    assert scored.coverage == 64
    assert scored.counts == {"strong": 1, "partial": 1, "gap": 1}
    assert (scored.must_total, scored.must_met, scored.must_coverage) == (2, 2, 1.0)
    assert scored.knockout_gaps == ()
    assert scored.label == "reasonable_fit"


def test_eight_percent_threshold_does_not_survive_a_knockout_gap() -> None:
    """80% coverage with one unmet knockout is reasonable, never a strong fit."""
    results = [_result("r1", importance="knockout", verdict="gap")] + [
        _result(f"r{index}", importance="weight", verdict="strong") for index in (2, 3, 4, 5)
    ]

    scored = score(results)

    assert scored.coverage == 80
    assert scored.knockout_gaps == ("r1",)
    assert scored.label == "reasonable_fit"


def test_all_strong_must_haves_is_a_strong_fit() -> None:
    results = [
        _result("r1", importance="knockout", verdict="strong"),
        _result("r2", importance="weight", verdict="strong"),
    ]

    scored = score(results)

    assert scored.coverage == 100
    assert scored.label == "strong_fit"


def test_low_coverage_is_a_stretch() -> None:
    results = [
        _result("r1", importance="weight", verdict="partial"),
        _result("r2", importance="weight", verdict="gap"),
    ]

    scored = score(results)

    assert scored.coverage == 25
    assert scored.label == "stretch"


def test_nothing_to_score_is_empty_not_a_crash() -> None:
    scored = score([])

    assert scored.coverage == 0
    assert scored.points == 0.0
    assert scored.total_weight == 0
    assert scored.must_coverage == 0.0
    assert scored.counts == {"strong": 0, "partial": 0, "gap": 0}
    assert scored.label == "stretch"


def test_counts_always_mention_every_verdict() -> None:
    scored = score([_result("r1", verdict="strong")])

    assert scored.counts == {"strong": 1, "partial": 0, "gap": 0}


def test_label_boundaries() -> None:
    assert fit_label(80, 0) == "strong_fit"
    assert fit_label(80, 1) == "reasonable_fit"
    assert fit_label(79, 0) == "reasonable_fit"
    assert fit_label(60, 1) == "reasonable_fit"
    assert fit_label(60, 2) == "stretch"
    assert fit_label(59, 0) == "stretch"
    assert fit_label(100, 3) == "stretch"


def test_as_dict_is_the_public_shape() -> None:
    payload = score([_result("r1", importance="weight", verdict="strong")]).as_dict()

    assert payload == {
        "label": "strong_fit",
        "coverage": 100,
        "counts": {"strong": 1, "partial": 0, "gap": 0},
        "must_have": {"met": 1, "total": 1, "coverage": 1.0},
    }
