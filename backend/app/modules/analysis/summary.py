"""The fit summary, assembled in code from verified matches.

No model writes any of this: every sentence is a fixed phrase chosen by a code
path, and every item points back to a requirement row. The summary never says
whether to apply.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Final

from app.modules.analysis.enums import Verdict
from app.modules.analysis.scoring import MUST_IMPORTANCES, RequirementResult, RequirementScore
from app.modules.analysis.voting import UNSTABLE_FLAG

MAX_STRONGEST: Final = 3
MAX_BIGGEST_GAPS: Final = 3


def _position_order(result: RequirementResult) -> int:
    return result.position


def _strongest(results: Sequence[RequirementResult]) -> list[dict[str, Any]]:
    """Strong matches on must-haves, in JD order, capped."""
    chosen = [
        result
        for result in results
        if result.verdict == Verdict.STRONG and result.importance in MUST_IMPORTANCES
    ]
    return [
        {
            "requirement_id": result.requirement_id,
            "text": result.text,
            "evidence_quote": result.evidence_quote,
        }
        for result in sorted(chosen, key=_position_order)[:MAX_STRONGEST]
    ]


def _biggest_gaps(results: Sequence[RequirementResult]) -> list[dict[str, Any]]:
    """Must-have gaps first, then must-have partials, each in JD order, capped."""
    gaps = [
        result
        for result in results
        if result.verdict == Verdict.GAP and result.importance in MUST_IMPORTANCES
    ]
    partials = [
        result
        for result in results
        if result.verdict == Verdict.PARTIAL and result.importance in MUST_IMPORTANCES
    ]
    ranked = sorted(gaps, key=_position_order) + sorted(partials, key=_position_order)
    return [
        {
            "requirement_id": result.requirement_id,
            "text": result.text,
            "verdict": result.verdict,
        }
        for result in ranked[:MAX_BIGGEST_GAPS]
    ]


def _knockout_gaps(
    results: Sequence[RequirementResult], knockout_gap_ids: Sequence[str]
) -> list[dict[str, Any]]:
    by_id = {result.requirement_id: result for result in results}
    gaps: list[dict[str, Any]] = []
    for requirement_id in knockout_gap_ids:
        result = by_id.get(requirement_id)
        gaps.append(
            {
                "requirement_id": requirement_id,
                "text": result.text if result is not None else "",
            }
        )
    return gaps


def build_summary(
    results: Sequence[RequirementResult],
    *,
    scored: RequirementScore,
    constraint_flags: Sequence[dict[str, Any]] = (),
) -> dict[str, Any]:
    unstable_count = sum(1 for result in results if UNSTABLE_FLAG in result.flags)
    knockout_gaps = _knockout_gaps(results, scored.knockout_gaps)
    return {
        **scored.as_dict(),
        "knockout_gaps": knockout_gaps,
        "strongest": _strongest(results),
        "biggest_gaps": _biggest_gaps(results),
        "unstable_count": unstable_count,
        "constraint_flags": list(constraint_flags),
    }
