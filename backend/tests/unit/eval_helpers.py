"""Builders shared by the eval-harness tests.

They live here so each test module reads as behaviour, not as setup. The
defaults describe a small healthy run; every test overrides only the field it
is about.
"""

from __future__ import annotations

from typing import Any

from app.eval_metrics import CaseResult, Outcome


def payload(
    requirements: list[tuple[str, str]],
    matches: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "requirements": [{"id": key, "text": text} for key, text in requirements],
        "matches": matches or [],
        "suggestions": [],
        "cover_note": {"text": ""},
    }


def case(
    *,
    case_id: str = "case",
    outcomes: list[Outcome] | None = None,
    extracted_total: int = 1,
    extracted_matched: int = 1,
    unsupported: int = 0,
    tokens: int = 100,
    latency_ms: int = 1000,
    expect: str = "analysis",
    actual: str = "analysis",
) -> CaseResult:
    return CaseResult(
        case_id=case_id,
        outcomes=outcomes or [],
        extracted_total=extracted_total,
        extracted_matched=extracted_matched,
        unsupported=unsupported,
        tokens=tokens,
        latency_ms=latency_ms,
        expect=expect,
        actual=actual,
    )


def outcome(verdict: str, gold: str, *, votes: dict[str, int] | None = None) -> Outcome:
    return Outcome(
        gold_text="requirement",
        gold_verdict=gold,
        verdict=verdict,
        votes=votes if votes is not None else {verdict: 3},
    )


def metrics(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "agreement": 0.9,
        "stability": 0.95,
        "structuring_accuracy": 0.95,
        "ungrounded": 0,
        "unsupported": 0,
        "requirements": 3,
        "cases": 1,
        "analysed_cases": 1,
        "refusals": 0,
        "refusals_correct": 0,
    }
    base.update(overrides)
    return base
