"""What the eval harness measures, and when a run is not mergeable.

These functions are pure: they take the per-case results the runner produced and
return numbers or a list of objections. Nothing here calls a model, so the
arithmetic can be pinned by tests that need no corpus.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Final

# M1/M2/M8 targets. A run below any of these is blocking.
#
# Lowered from 80/90/90 to a flat 75 by the owner on 2026-11-12 (Ruling D15), after the
# gate was measured on the real corpus for the first time. The cost is stated there and
# not hidden: one requirement in four may now be judged wrongly and the gate still passes.
TARGETS: Final[dict[str, float]] = {
    "agreement": 0.75,
    "stability": 0.75,
    "structuring_accuracy": 0.75,
}
AGREEMENT_DROP_LIMIT: Final = 2.0  # percentage points, PRD §10

# A case can be a page that must be refused instead of a pair that must be judged.
# Refusing a page that is not one job post is a feature, so it needs a metric.
REFUSALS: Final = frozenset({"JD_NOT_FOUND", "JD_MULTIPLE_JOBS"})

_WORD: Final = re.compile(r"[a-z0-9]+")


class EvalError(Exception):
    """The eval set itself is unusable: a missing pair, an unknown verdict."""


def normalize_text(text: str) -> str:
    """Lowercase word tokens. Punctuation and spacing must not decide a match."""
    return " ".join(_WORD.findall(text.lower()))


def overlap(left: str, right: str) -> float:
    """Shared tokens over the smaller side.

    Not Jaccard: my label for a requirement is short ("strong Go") while the
    extractor writes a full sentence, and Jaccard would score that pair as a
    miss. Containment asks the question that matters: is my label inside it?
    """
    a = set(normalize_text(left).split())
    b = set(normalize_text(right).split())
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def match_requirements(
    gold: list[str], extracted: list[str], *, threshold: float = 0.5
) -> dict[int, int]:
    """Gold index -> extracted index, best overlap first, each item used once."""
    scored = [
        (overlap(gold_text, extracted_text), gold_index, extracted_index)
        for gold_index, gold_text in enumerate(gold)
        for extracted_index, extracted_text in enumerate(extracted)
    ]
    scored.sort(reverse=True)
    mapping: dict[int, int] = {}
    used_gold: set[int] = set()
    used_extracted: set[int] = set()
    for score, gold_index, extracted_index in scored:
        if score < threshold:
            break
        if gold_index in used_gold or extracted_index in used_extracted:
            continue
        used_gold.add(gold_index)
        used_extracted.add(extracted_index)
        mapping[gold_index] = extracted_index
    return mapping


@dataclass(frozen=True, slots=True)
class Outcome:
    """One requirement compared: what I labelled, what the pipeline said."""

    gold_text: str
    gold_verdict: str
    verdict: str | None = None
    votes: dict[str, int] = field(default_factory=dict)
    evidence_quote: str | None = None
    grounded: bool = True

    @property
    def agree(self) -> bool:
        return self.verdict == self.gold_verdict

    def is_stable(self, match_runs: int) -> bool:
        """Unanimous across the runs that voted for this requirement."""
        votes = [count for count in self.votes.values() if count]
        return not votes or max(votes) == match_runs

    def as_dict(self, match_runs: int) -> dict[str, Any]:
        return {
            "gold_text": self.gold_text,
            "gold_verdict": self.gold_verdict,
            "verdict": self.verdict,
            "votes": dict(self.votes),
            # The quote is the only way to tell a wrong verdict from a fabricated
            # one after the run, and the throwaway database is deleted.
            "evidence_quote": self.evidence_quote,
            "grounded": self.grounded,
            "agree": self.agree,
            "stable": self.is_stable(match_runs),
        }


@dataclass(frozen=True, slots=True)
class CaseResult:
    case_id: str
    outcomes: list[Outcome]
    extracted_total: int
    extracted_matched: int
    unsupported: int
    tokens: int
    latency_ms: int
    expect: str = "analysis"
    actual: str = "analysis"

    @property
    def satisfied(self) -> bool:
        """The run ended the way the case said it should: judged, or refused."""
        return self.actual == self.expect

    def as_dict(self, match_runs: int) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "expect": self.expect,
            "actual": self.actual,
            "satisfied": self.satisfied,
            "extracted_total": self.extracted_total,
            "extracted_matched": self.extracted_matched,
            "unsupported": self.unsupported,
            "tokens": self.tokens,
            "latency_ms": self.latency_ms,
            "requirements": [outcome.as_dict(match_runs) for outcome in self.outcomes],
        }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _percentile(values: list[int], fraction: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(fraction * (len(ordered) - 1)))]


def summarize(results: list[CaseResult], match_runs: int) -> dict[str, Any]:
    """The gate metrics, computed from stored data only.

    Stability reads the vote distribution the pipeline already stores: every
    requirement was judged `match_runs` times, so a unanimous vote is the
    "same case three times" check that M2 asks for, without paying for it twice.
    """
    # A refusal case has no requirements and no latency of its own, so it must not
    # dilute the judgment metrics or drag the latency percentiles towards zero.
    analysed = [result for result in results if result.expect not in REFUSALS]
    refusals = [result for result in results if result.expect in REFUSALS]
    outcomes = [outcome for result in analysed for outcome in result.outcomes]
    latencies = [result.latency_ms for result in analysed]
    return {
        "agreement": _ratio(sum(1 for outcome in outcomes if outcome.agree), len(outcomes)),
        "stability": _ratio(
            sum(1 for outcome in outcomes if outcome.is_stable(match_runs)), len(outcomes)
        ),
        "structuring_accuracy": _ratio(
            sum(result.extracted_matched for result in analysed),
            sum(result.extracted_total for result in analysed),
        ),
        "ungrounded": sum(1 for outcome in outcomes if not outcome.grounded),
        "unsupported": sum(result.unsupported for result in analysed),
        "requirements": len(outcomes),
        "cases": len(results),
        "analysed_cases": len(analysed),
        "refusals": len(refusals),
        "refusals_correct": sum(1 for result in refusals if result.satisfied),
        "tokens": sum(result.tokens for result in analysed),
        "latency_p50_ms": _percentile(latencies, 0.50),
        "latency_p95_ms": _percentile(latencies, 0.95),
    }


# What `--update-baseline` is allowed to write. The report it projects embeds
# gold requirement text and the evidence quotes the model returned, i.e. CV and
# JD text, and the baseline outlives the run and gets copied around.
BASELINE_KEYS: Final[tuple[str, ...]] = (
    "generated_at",
    "model",
    "prompt_bundle",
    "match_runs",
    "case_ids",
    "metrics",
    "targets",
    "passed",
)


def baseline_document(report: dict[str, Any]) -> dict[str, Any]:
    """The metrics-only projection of a report that a baseline may hold."""
    return {key: report[key] for key in BASELINE_KEYS if key in report}


def _same_case_set(baseline: dict[str, Any] | None, case_ids: tuple[str, ...]) -> bool:
    """A baseline only means something when it measured the same cases.

    The set grows as real pages arrive. Comparing this run with a baseline taken over
    a smaller and easier set reports the change in the set as if it were a change in
    quality, in either direction.

    `eval/baseline.json` is deliberately metrics-only, because a full report embeds CV
    and JD text, so it cannot carry case ids. When ids are absent, the recorded case
    count is the only evidence available; when neither is present the baseline is not
    comparable, and a silent pass is worse than no comparison at all.
    """
    recorded = tuple(str(item) for item in (baseline or {}).get("case_ids") or ())
    if recorded:
        return recorded == tuple(sorted(case_ids))
    count = (baseline or {}).get("cases")
    return isinstance(count, int) and count == len(case_ids)


def regressions(
    metrics: dict[str, Any],
    baseline: dict[str, Any] | None,
    *,
    case_ids: tuple[str, ...] = (),
) -> list[str]:
    """Why this run must not be merged. A missing baseline is a first run."""
    # A subset that contains only refusal pages measures no judgment at all, and
    # an empty denominator would score the target as a failure.
    scored = {"agreement", "stability"} if metrics["requirements"] else set()
    if metrics["analysed_cases"]:
        scored.add("structuring_accuracy")
    problems = [
        f"{name}: {float(metrics[name]):.4f} is below the {target:.2f} target"
        for name, target in TARGETS.items()
        if name in scored and float(metrics[name]) < target
    ]
    if metrics["ungrounded"]:
        problems.append(f"ungrounded: {metrics['ungrounded']} quote(s) not found in the CV")
    if metrics["unsupported"]:
        problems.append(f"unsupported: {metrics['unsupported']} case(s) leaked an unknown number")
    previous = float((baseline or {}).get("metrics", {}).get("agreement", 0.0))
    drop = (previous - float(metrics["agreement"])) * 100
    if previous and _same_case_set(baseline, case_ids) and drop > AGREEMENT_DROP_LIMIT:
        problems.append(f"agreement dropped {drop:.2f} points against the baseline")
    return problems
