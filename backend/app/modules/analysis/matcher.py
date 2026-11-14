"""S2..S4: one call per requirement per run, grounded, then voted.

Grounded first, voted second: a paraphrase that no run can point at in the CV
never reaches the tally, so a majority cannot launder an invented quote.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, cast

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.modules.analysis.call_ledger import record_call
from app.modules.analysis.enums import LlmOutcome, Step
from app.modules.analysis.grounding import Grounded, ground
from app.modules.analysis.ports import LLMClient, LLMError, LlmRequest, LlmResponse
from app.modules.analysis.prompts import PromptText, fill, load_prompt
from app.modules.analysis.schemas import MatchVerdict, load_payload
from app.modules.analysis.scoring import RequirementResult
from app.modules.analysis.views import RequirementView
from app.modules.analysis.voting import Vote, tally
from app.shared.clock import Clock
from app.shared.errors import AppError

MATCH_PROMPT: Final = "match"
# v2 adds the gap/partial/strong ladder and the one-contiguous-span quote rule.
MATCH_PROMPT_VERSION: Final = "v2"
MATCH_SCHEMA: Final = "match_verdict"


def _match_request(
    prompt: PromptText, *, requirement: RequirementView, cv_text: str
) -> LlmRequest:
    return LlmRequest(
        step=Step.S2_MATCH,
        prompt_version=prompt.ref.prompt_version,
        system=prompt.system,
        user=fill(
            prompt.user_template,
            {"requirement_text": requirement.text, "cv_text": cv_text},
        ),
        schema_name=MATCH_SCHEMA,
    )


@dataclass(frozen=True, slots=True)
class MatchResult:
    results: list[RequirementResult] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "matches": [
                {
                    "requirement_id": item.requirement_id,
                    "verdict": item.verdict,
                    "evidence_quote": item.evidence_quote,
                    "rationale": item.rationale,
                    "votes": dict(item.votes),
                    "agreement": item.agreement,
                    "flags": list(item.flags),
                }
                for item in self.results
            ],
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
        }


def _combine(requirement: RequirementView, runs: Sequence[Grounded]) -> RequirementResult:
    """Vote over grounded runs so a paraphrase can never win a majority."""
    vote: Vote = tally([run.verdict for run in runs])
    winner = next((run for run in runs if run.verdict == vote.verdict), None)
    flags = list(vote.flags)
    for run in runs:
        flags.extend(flag for flag in run.flags if flag not in flags)
    return RequirementResult(
        requirement_id=requirement.id,
        position=requirement.position,
        text=requirement.text,
        importance=requirement.importance,
        verdict=vote.verdict,
        evidence_quote=winner.evidence_quote if winner is not None else None,
        rationale=(winner.rationale or None) if winner is not None else None,
        keywords=tuple(requirement.keywords),
        votes=vote.votes,
        agreement=vote.agreement,
        flags=tuple(flags),
    )


@dataclass(frozen=True, slots=True)
class Matcher:
    """S2..S4: one call per requirement per run, grounded, then voted.

    Bounded by a semaphore rather than a queue: the concurrency ceiling comes
    from settings, and the calls are short enough that a broker buys nothing.
    """

    llm: LLMClient
    session_factory: sessionmaker[Session]
    prompts_dir: Path
    model: str
    clock: Clock
    runs: int = 3
    max_concurrency: int = 2

    async def match(self, *, requirements: Sequence[RequirementView], cv_text: str) -> MatchResult:
        prompt = load_prompt(self.prompts_dir, MATCH_PROMPT, MATCH_PROMPT_VERSION)
        plan = [(item, run) for item in requirements for run in range(max(1, self.runs))]
        semaphore = asyncio.Semaphore(max(1, self.max_concurrency))
        graded = await asyncio.gather(
            *[
                self._one(prompt, requirement=item, cv_text=cv_text, semaphore=semaphore)
                for item, _ in plan
            ]
        )
        grouped: dict[str, list[Grounded]] = {item.id: [] for item in requirements}
        tokens_in = 0
        tokens_out = 0
        for (item, _), (grounded, used_in, used_out) in zip(plan, graded, strict=True):
            grouped[item.id].append(grounded)
            tokens_in += used_in
            tokens_out += used_out
        return MatchResult(
            results=[_combine(item, grouped[item.id]) for item in requirements],
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

    async def _one(
        self,
        prompt: PromptText,
        *,
        requirement: RequirementView,
        cv_text: str,
        semaphore: asyncio.Semaphore,
    ) -> tuple[Grounded, int, int]:
        request = _match_request(prompt, requirement=requirement, cv_text=cv_text)
        response = await self._complete(request, semaphore)
        payload = self._payload(request, response)
        self._record(request, LlmOutcome.OK, response)
        return (
            ground(
                verdict=payload.verdict,
                evidence_quote=payload.evidence_quote,
                cv_text=cv_text,
                rationale=payload.rationale,
            ),
            response.tokens_in,
            response.tokens_out,
        )

    async def _complete(
        self, request: LlmRequest, semaphore: asyncio.Semaphore
    ) -> LlmResponse:
        async with semaphore:
            try:
                return await self.llm.complete(request)
            except LLMError as exc:
                self._record(request, LlmOutcome.ERROR)
                raise AppError(exc.code, str(exc), {"step": request.step}) from exc

    def _payload(self, request: LlmRequest, response: LlmResponse) -> MatchVerdict:
        try:
            return cast(MatchVerdict, load_payload(MATCH_SCHEMA, response.payload))
        except ValidationError as exc:
            self._record(request, LlmOutcome.INVALID)
            raise AppError(
                "LLM_SCHEMA_INVALID",
                "The model returned a result that does not match the schema.",
                {"step": request.step},
            ) from exc

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
