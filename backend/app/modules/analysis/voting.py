"""S4: majority vote across the N runs, with a conservative tie-break.

Three runs on the same input can disagree. A tie never resolves upward: the
lower verdict wins, because an optimistic tie would credit evidence the CV may
not have.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from app.modules.analysis.enums import Verdict

# Conservative order. A tie falls back to the lowest, never the highest.
CONSERVATIVE_ORDER: Final[dict[str, int]] = {
    Verdict.GAP: 0,
    Verdict.PARTIAL: 1,
    Verdict.STRONG: 2,
}

STABILITY_THRESHOLD: Final = 0.67
UNSTABLE_FLAG: Final = "unstable"


@dataclass(frozen=True, slots=True)
class Vote:
    verdict: str
    votes: dict[str, int]
    agreement: float
    flags: tuple[str, ...] = ()

    @property
    def unstable(self) -> bool:
        return UNSTABLE_FLAG in self.flags


def tally(verdicts: Sequence[str]) -> Vote:
    """Majority wins; a tie resolves to the most conservative tied verdict."""
    if not verdicts:
        return Vote(
            verdict=Verdict.GAP,
            votes={},
            agreement=0.0,
            flags=(UNSTABLE_FLAG,),
        )
    counts = Counter(verdicts)
    best = max(counts.values())
    winners = [verdict for verdict, count in counts.items() if count == best]
    verdict = min(winners, key=lambda item: CONSERVATIVE_ORDER.get(item, -1))
    # Rounded before the threshold check on purpose: 2 of 3 runs is a majority,
    # and 0.6666... must not be reported as unstable at a 0.67 threshold.
    agreement = round(best / len(verdicts), 2)
    flags = (UNSTABLE_FLAG,) if agreement < STABILITY_THRESHOLD else ()
    return Vote(
        verdict=verdict,
        votes=dict(sorted(counts.items())),
        agreement=agreement,
        flags=flags,
    )
