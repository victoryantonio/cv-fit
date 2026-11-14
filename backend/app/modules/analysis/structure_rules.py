"""S1 acceptance: what survives from the model's answer, decided without IO.

Pure functions so the acceptance rules can be read and tested on their own: a
quote that is not literally in the pasted text is dropped, twins are merged, and
the list is cut by importance. Nothing here touches a session or the network.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Final

from app.modules.analysis.enums import ExtractionStatus
from app.modules.analysis.models import JdRequirement
from app.modules.analysis.schemas import JdStructure
from app.modules.analysis.views import IMPORTANCE_ORDER
from app.shared.text import contains_quote, normalise

MAX_REQUIREMENTS: Final = 40
MIN_EXPECTED_REQUIREMENTS: Final = 5


def _dedupe(items: Iterable[Any]) -> tuple[list[Any], int]:
    seen: set[str] = set()
    kept: list[Any] = []
    removed = 0
    for item in items:
        key = normalise(item.text)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        kept.append(item)
    return kept, removed


def _cut_by_importance(items: list[Any]) -> list[Any]:
    """Stable sort by importance then original order, then cap the list."""
    ranked = sorted(items, key=lambda item: IMPORTANCE_ORDER.get(item.importance, 9))
    return ranked[:MAX_REQUIREMENTS]


def _verify_quotes(items: list[Any], raw_text: str) -> tuple[list[Any], int]:
    verified = [item for item in items if contains_quote(raw_text, item.jd_quote)]
    return verified, len(items) - len(verified)


def status_for(structure: JdStructure) -> str:
    if not structure.is_job_post:
        return ExtractionStatus.JD_NOT_FOUND
    if structure.job_count > 1:
        return ExtractionStatus.JD_MULTIPLE_JOBS
    return ExtractionStatus.OK


@dataclass(frozen=True, slots=True)
class Prepared:
    """S1 acceptance, decided before anything is written."""

    status: str
    requirements: list[Any]
    dropped: int = 0
    duplicates: int = 0
    warnings: tuple[str, ...] = ()


def prepared(structure: JdStructure, raw_text: str) -> Prepared:
    """Drop quotes that are not in the pasted text, merge twins, keep the top ones."""
    status = status_for(structure)
    if status != ExtractionStatus.OK:
        return Prepared(status=status, requirements=[])
    verified, dropped = _verify_quotes(list(structure.requirements), raw_text)
    unique, duplicates = _dedupe(verified)
    requirements = _cut_by_importance(unique)
    warnings = ("few_requirements",) if len(requirements) < MIN_EXPECTED_REQUIREMENTS else ()
    return Prepared(
        status=status,
        requirements=requirements,
        dropped=dropped,
        duplicates=duplicates,
        warnings=warnings,
    )


def requirement_models(extraction_id: str, requirements: list[Any]) -> list[JdRequirement]:
    """Position is the order the model's importance cut left them in."""
    return [
        JdRequirement(
            extraction_id=extraction_id,
            position=position,
            text=item.text,
            category=item.category,
            importance=item.importance,
            keywords=list(item.keywords),
            jd_quote=item.jd_quote,
        )
        for position, item in enumerate(requirements)
    ]
