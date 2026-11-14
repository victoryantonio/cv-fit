"""The summary is assembled in code: fixed phrases, JD order, hard caps."""

from __future__ import annotations

from app.modules.analysis.scoring import RequirementResult, score
from app.modules.analysis.summary import MAX_BIGGEST_GAPS, MAX_STRONGEST, build_summary
from app.modules.analysis.voting import UNSTABLE_FLAG


def _result(
    requirement_id: str,
    *,
    position: int,
    importance: str = "weight",
    verdict: str = "gap",
    quote: str | None = None,
    flags: tuple[str, ...] = (),
) -> RequirementResult:
    return RequirementResult(
        requirement_id=requirement_id,
        position=position,
        text=f"Requirement {requirement_id}",
        importance=importance,
        verdict=verdict,
        evidence_quote=quote,
        flags=flags,
    )


def test_strongest_lists_only_strong_must_haves_in_jd_order() -> None:
    results = [
        _result("r3", position=3, verdict="strong", quote="Led the ledger rewrite."),
        _result("r1", position=1, verdict="strong", quote="Six years of Python."),
        _result("r2", position=2, importance="nice", verdict="strong", quote="Wrote docs."),
        _result("r4", position=4, verdict="partial", quote="Some SQL."),
    ]

    summary = build_summary(results, scored=score(results))

    assert [item["requirement_id"] for item in summary["strongest"]] == ["r1", "r3"]
    assert summary["strongest"][0]["evidence_quote"] == "Six years of Python."


def test_strongest_is_capped() -> None:
    results = [
        _result(f"r{index}", position=index, verdict="strong", quote=f"Quote {index}.")
        for index in range(1, 6)
    ]

    summary = build_summary(results, scored=score(results))

    assert len(summary["strongest"]) == MAX_STRONGEST
    assert [item["requirement_id"] for item in summary["strongest"]] == ["r1", "r2", "r3"]


def test_biggest_gaps_put_misses_before_partials() -> None:
    results = [
        _result("r1", position=1, verdict="partial"),
        _result("r2", position=2, verdict="gap"),
        _result("r3", position=3, importance="nice", verdict="gap"),
        _result("r4", position=4, verdict="gap"),
    ]

    summary = build_summary(results, scored=score(results))

    assert [item["requirement_id"] for item in summary["biggest_gaps"]] == ["r2", "r4", "r1"]
    assert summary["biggest_gaps"][0]["verdict"] == "gap"
    assert summary["biggest_gaps"][-1]["verdict"] == "partial"


def test_biggest_gaps_is_capped() -> None:
    results = [_result(f"r{index}", position=index, verdict="gap") for index in range(1, 6)]

    summary = build_summary(results, scored=score(results))

    assert len(summary["biggest_gaps"]) == MAX_BIGGEST_GAPS


def test_knockout_gaps_carry_their_requirement_text() -> None:
    results = [
        _result("r1", position=1, importance="knockout", verdict="gap"),
        _result("r2", position=2, verdict="strong"),
    ]

    summary = build_summary(results, scored=score(results))

    assert summary["knockout_gaps"] == [{"requirement_id": "r1", "text": "Requirement r1"}]


def test_unstable_runs_are_counted() -> None:
    results = [
        _result("r1", position=1, verdict="gap", flags=(UNSTABLE_FLAG,)),
        _result("r2", position=2, verdict="strong"),
    ]

    summary = build_summary(results, scored=score(results))

    assert summary["unstable_count"] == 1


def test_constraint_flags_are_passed_through_untouched() -> None:
    flags = [{"kind": "work_mode", "status": "conflict", "note": "Remote only."}]

    summary = build_summary([], scored=score([]), constraint_flags=flags)

    assert summary["constraint_flags"] == flags


def test_summary_reuses_the_scored_block_and_never_advises() -> None:
    results = [_result("r1", position=1, verdict="strong", quote="Quote.")]

    summary = build_summary(results, scored=score(results))

    assert summary["label"] == "strong_fit"
    assert summary["coverage"] == 100
    assert summary["must_have"] == {"met": 1, "total": 1, "coverage": 1.0}
    assert not {"recommendation", "decision", "apply", "skip"} & set(summary)
