"""S5 plus S6: suggestions, then the fabrication guard, in that order.

The `suggest` prompt is told to return nothing rather than invent, so a gap with
no adjacent CV evidence would otherwise disappear from the packet. Those gaps get
a `gap_note` built here in code: no model call, no rewrite text, nothing that can
be fabricated. Every suggestion, generated or derived, passes the guard before it
is allowed to reach storage.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, cast

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.modules.analysis.enums import (
    GuardStatus,
    LlmOutcome,
    Step,
    SuggestionScope,
    SuggestionTarget,
    SuggestionType,
    Verdict,
)
from app.modules.analysis.guards import GuardContext, check_suggestion
from app.modules.analysis.models import Suggestion
from app.modules.analysis.ports import LLMClient, LLMError, LlmRequest, LlmResponse
from app.modules.analysis.prompts import fill, load_prompt
from app.modules.analysis.schemas import SuggestionBatch, SuggestionOut, load_payload
from app.modules.analysis.scoring import RequirementResult
from app.modules.analysis.steps import IMPORTANCE_ORDER, record_call
from app.shared.errors import AppError

PROMPT_NAME: Final = "suggest"
SCHEMA_NAME: Final = "suggestion_batch"
MAX_GAPS: Final = 20

#: Gap notes quote the requirement, so leave room for the prefix inside 400 chars.
NOTE_PREFIX: Final = "No CV evidence for: "
NOTE_ROOM: Final = 400 - len(NOTE_PREFIX)


@dataclass(frozen=True, slots=True)
class SuggestionView:
    """One suggestion after the guard. Ids and decisions are added at persist."""

    requirement_id: str | None
    position: int | None
    type: str
    scope: str
    target_section: str
    original_text: str | None
    proposed_text: str | None
    rationale: str | None
    guard_status: str
    guard_reason: str | None

    @property
    def visible(self) -> bool:
        return self.guard_status == GuardStatus.PASS


@dataclass(frozen=True, slots=True)
class SuggestionResult:
    suggestions: tuple[SuggestionView, ...] = ()
    tokens_in: int = 0
    tokens_out: int = 0
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def hidden(self) -> int:
        return sum(1 for item in self.suggestions if not item.visible)


@dataclass(frozen=True, slots=True)
class Suggester:
    llm: LLMClient
    session_factory: sessionmaker[Session]
    prompts_dir: Path
    model: str

    async def suggest(
        self,
        *,
        results: Sequence[RequirementResult],
        cv_text: str,
        section_texts: dict[str, str] | None = None,
    ) -> SuggestionResult:
        targets = _targets(results)
        if not targets:
            return SuggestionResult()
        request = self._request(targets=targets, cv_text=cv_text)
        response = await self._complete(request)
        self._record(request, LlmOutcome.OK, response)
        try:
            batch = cast(SuggestionBatch, load_payload(SCHEMA_NAME, response.payload))
        except ValidationError as exc:
            self._record(request, LlmOutcome.INVALID)
            raise AppError(
                "LLM_SCHEMA_INVALID",
                "The model returned a result that does not match the schema.",
                {"step": request.step},
            ) from exc
        paired = _pair(batch.suggestions, targets)
        views = [_view(out, target, cv_text, section_texts) for out, target in paired]
        notes = _gap_notes(targets, paired)
        views.extend(_view(note, target, cv_text, section_texts) for note, target in notes)
        return SuggestionResult(
            suggestions=tuple(views),
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
        )

    def _request(self, *, targets: Sequence[RequirementResult], cv_text: str) -> LlmRequest:
        prompt = load_prompt(self.prompts_dir, PROMPT_NAME)
        return LlmRequest(
            step=Step.S5_SUGGEST,
            prompt_version=prompt.ref.prompt_version,
            system=prompt.system,
            user=fill(prompt.user_template, {"gap_list": _gap_list(targets), "cv_text": cv_text}),
            schema_name=SCHEMA_NAME,
        )

    async def _complete(self, request: LlmRequest) -> LlmResponse:
        try:
            return await self.llm.complete(request)
        except LLMError as exc:
            self._record(request, LlmOutcome.ERROR)
            raise AppError(exc.code, str(exc), {"step": request.step}) from exc

    def _record(
        self, request: LlmRequest, outcome: str, response: LlmResponse | None = None
    ) -> None:
        with self.session_factory() as session:
            record_call(
                session,
                request=request,
                model=self.model,
                outcome=outcome,
                tokens_in=response.tokens_in if response else 0,
                tokens_out=response.tokens_out if response else 0,
                latency_ms=response.latency_ms if response else 0,
            )
            session.commit()


def _targets(results: Sequence[RequirementResult]) -> list[RequirementResult]:
    """Partial and gap requirements, most important first, capped."""
    open_items = [item for item in results if item.verdict in {Verdict.PARTIAL, Verdict.GAP}]
    ranked = sorted(
        open_items,
        key=lambda item: (IMPORTANCE_ORDER.get(item.importance, 9), item.position),
    )
    return ranked[:MAX_GAPS]


def _gap_list(targets: Sequence[RequirementResult]) -> str:
    """Numbered from zero so `requirement_index` means the same thing here."""
    return "\n".join(
        f"{index}) [{item.importance}] {item.verdict} - {item.text}"
        for index, item in enumerate(targets)
    )


def _pair(
    suggestions: Sequence[SuggestionOut], targets: Sequence[RequirementResult]
) -> list[tuple[SuggestionOut, RequirementResult | None]]:
    paired: list[tuple[SuggestionOut, RequirementResult | None]] = []
    for item in suggestions:
        index = item.requirement_index
        target = targets[index] if index is not None and index < len(targets) else None
        paired.append((item, target))
    return paired


def _gap_notes(
    targets: Sequence[RequirementResult],
    paired: Sequence[tuple[SuggestionOut, RequirementResult | None]],
) -> list[tuple[SuggestionOut, RequirementResult]]:
    """A gap the model would not touch is reported as a gap, not papered over."""
    covered = {
        target.requirement_id
        for item, target in paired
        if target is not None and item.type is not SuggestionType.GAP_NOTE
    }
    return [
        (_note(target), target)
        for target in targets
        if target.verdict == Verdict.GAP and target.requirement_id not in covered
    ]


def _note(target: RequirementResult) -> SuggestionOut:
    return SuggestionOut(
        type=SuggestionType.GAP_NOTE,
        scope=SuggestionScope.GENERAL,
        target_section=SuggestionTarget.OTHER,
        rationale=f"{NOTE_PREFIX}{target.text[:NOTE_ROOM]}",
    )


def _view(
    suggestion: SuggestionOut,
    target: RequirementResult | None,
    cv_text: str,
    section_texts: dict[str, str] | None,
) -> SuggestionView:
    context = GuardContext.build(
        cv_text=cv_text,
        section_texts=section_texts,
        verdict=_verdict(target),
    )
    result = check_suggestion(suggestion, context)
    return SuggestionView(
        requirement_id=target.requirement_id if target is not None else None,
        position=target.position if target is not None else None,
        type=suggestion.type.value,
        scope=suggestion.scope.value,
        target_section=suggestion.target_section.value,
        original_text=suggestion.original_text,
        proposed_text=suggestion.proposed_text,
        rationale=suggestion.rationale or None,
        guard_status=result.status,
        guard_reason=result.detail,
    )


def _verdict(target: RequirementResult | None) -> Verdict | None:
    if target is None:
        return None
    return Verdict(target.verdict) if target.verdict in set(Verdict) else None


def rows_for(analysis_id: str, result: SuggestionResult) -> list[Suggestion]:
    """Stored rows, guard verdict included, ready for one transaction."""
    return [
        Suggestion(
            analysis_id=analysis_id,
            requirement_id=item.requirement_id,
            type=item.type,
            scope=item.scope,
            target_section=item.target_section,
            original_text=item.original_text,
            proposed_text=item.proposed_text,
            rationale=item.rationale,
            guard_status=item.guard_status,
            guard_reason=item.guard_reason,
        )
        for item in result.suggestions
    ]


def as_payload(row: Suggestion) -> dict[str, Any]:
    return {
        "id": row.id,
        "requirement_id": row.requirement_id,
        "type": row.type,
        "scope": row.scope,
        "target_section": row.target_section,
        "original_text": row.original_text,
        "proposed_text": row.proposed_text,
        "rationale": row.rationale,
        "guard_status": row.guard_status,
        "guard_reason": row.guard_reason,
        "decision": row.decision,
        "decision_reason": row.decision_reason,
    }


def visible_payloads(rows: Sequence[Suggestion]) -> list[dict[str, Any]]:
    """Violations are hidden by default; they only surface on request."""
    return [as_payload(row) for row in rows if row.guard_status == GuardStatus.PASS]


def provenance(rows: Sequence[Suggestion]) -> dict[str, Any]:
    """Every suggestion is counted, including the ones the guard threw out."""
    by_rule: dict[str, int] = {}
    for row in rows:
        if row.guard_status == GuardStatus.PASS:
            continue
        code = row.guard_status.removeprefix("rejected_")
        by_rule[code] = by_rule.get(code, 0) + 1
    hidden = sum(by_rule.values())
    return {
        "total": len(rows),
        "visible": len(rows) - hidden,
        "hidden": hidden,
        "rejected_by_rule": by_rule,
    }
