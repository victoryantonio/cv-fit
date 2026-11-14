"""Coverage math. A pure function of stored verdicts, never stored itself.

Nothing derived lives in the database: change a weight here and every existing
analysis re-derives on read, so a stale score is impossible by construction.
The 80/60 thresholds exist in this module only.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Final

from app.modules.analysis.enums import Importance, Verdict

MUST_WEIGHT: Final = 3
NICE_WEIGHT: Final = 1

STRONG_VALUE: Final = 1.0
PARTIAL_VALUE: Final = 0.5
GAP_VALUE: Final = 0.0

VERDICT_VALUES: Final[dict[str, float]] = {
    Verdict.STRONG: STRONG_VALUE,
    Verdict.PARTIAL: PARTIAL_VALUE,
    Verdict.GAP: GAP_VALUE,
}

MUST_IMPORTANCES: Final[frozenset[str]] = frozenset({Importance.KNOCKOUT, Importance.WEIGHT})
MET: Final[frozenset[str]] = frozenset({Verdict.STRONG, Verdict.PARTIAL})

FIT_STRONG: Final = "strong_fit"
FIT_REASONABLE: Final = "reasonable_fit"
FIT_STRETCH: Final = "stretch"

STRONG_FIT_COVERAGE: Final = 80
REASONABLE_FIT_COVERAGE: Final = 60
MAX_KNOCKOUT_GAPS_FOR_REASONABLE: Final = 1


@dataclass(frozen=True, slots=True)
class RequirementResult:
    """One requirement with its verified verdict, ready to score or summarise."""

    requirement_id: str
    position: int
    text: str
    importance: str
    verdict: str
    evidence_quote: str | None = None
    rationale: str | None = None
    keywords: tuple[str, ...] = ()
    votes: dict[str, int] = field(default_factory=dict)
    agreement: float = 1.0
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RequirementScore:
    coverage: int
    points: float
    total_weight: int
    counts: dict[str, int]
    must_total: int
    must_met: int
    must_coverage: float
    knockout_gaps: tuple[str, ...]
    label: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "coverage": self.coverage,
            "counts": dict(self.counts),
            "must_have": {
                "met": self.must_met,
                "total": self.must_total,
                "coverage": self.must_coverage,
            },
        }


def weight_of(importance: str) -> int:
    return MUST_WEIGHT if importance in MUST_IMPORTANCES else NICE_WEIGHT


def value_of(verdict: str) -> float:
    """An unknown verdict is worth nothing, never a guess."""
    return VERDICT_VALUES.get(verdict, GAP_VALUE)


def fit_label(coverage: int, knockout_gaps: int) -> str:
    if coverage >= STRONG_FIT_COVERAGE and knockout_gaps == 0:
        return FIT_STRONG
    if coverage >= REASONABLE_FIT_COVERAGE and knockout_gaps <= MAX_KNOCKOUT_GAPS_FOR_REASONABLE:
        return FIT_REASONABLE
    return FIT_STRETCH


def score(results: Sequence[RequirementResult]) -> RequirementScore:
    """Weighted coverage over the results given. Same input, same output."""
    tally: Counter[str] = Counter(result.verdict for result in results)
    points = 0.0
    total_weight = 0
    must_total = 0
    must_met = 0
    knockout_gaps: list[str] = []
    for result in results:
        weight = weight_of(result.importance)
        total_weight += weight
        points += weight * value_of(result.verdict)
        if weight == MUST_WEIGHT:
            must_total += 1
            if result.verdict in MET:
                must_met += 1
        if result.importance == Importance.KNOCKOUT and result.verdict == Verdict.GAP:
            knockout_gaps.append(result.requirement_id)
    coverage = round(100 * points / total_weight) if total_weight else 0
    return RequirementScore(
        coverage=coverage,
        points=round(points, 2),
        total_weight=total_weight,
        counts={verdict.value: tally.get(verdict, 0) for verdict in Verdict},
        must_total=must_total,
        must_met=must_met,
        must_coverage=round(must_met / must_total, 2) if must_total else 0.0,
        knockout_gaps=tuple(knockout_gaps),
        label=fit_label(coverage, len(knockout_gaps)),
    )
