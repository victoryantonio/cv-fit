"""S7 plus S8: the cover note, then its guard, in that order.

Only requirements whose verdict is `strong` reach the prompt, and each of them
carries the quote the matcher already grounded. A note is therefore written from
verified evidence and checked against the same evidence: a claim the CV cannot
back has nowhere to come from. One rejection is retried with the violation
spelled out; a second failure is stored as `rejected_<rule>` and the packet is
returned without a note rather than with an unverified one.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from pydantic import ValidationError
from sqlalchemy.orm import Session, sessionmaker

from app.modules.analysis.enums import GuardStatus, LlmOutcome, Step, Verdict
from app.modules.analysis.guards import (
    CoverClaim,
    CoverContext,
    GuardContext,
    check_cover_note,
)
from app.modules.analysis.ports import LLMClient, LLMError, LlmRequest, LlmResponse
from app.modules.analysis.prompts import PromptText, fill, load_prompt
from app.modules.analysis.schemas import CoverNoteDraft, JdStructure, load_payload
from app.modules.analysis.scoring import RequirementResult
from app.modules.analysis.steps import IMPORTANCE_ORDER, record_call
from app.shared.errors import AppError
from app.shared.text import words

PROMPT_NAME: Final = "cover_note"
SCHEMA_NAME: Final = "cover_note"

#: A third guard state: nothing was verified, so no draft was ever requested.
NO_STRONG_MATCHES: Final = "no_strong_matches"

#: Keywords shorter than this ("go", "r") are too generic to forbid in prose.
MIN_KEYWORD_LENGTH: Final = 3

VIOLATION_BLOCK: Final = """
The previous attempt was rejected by the verifier: {detail}
Write a new note that does not repeat that problem. The rules above still apply.
"""


@dataclass(frozen=True, slots=True)
class CoverNoteView:
    """One attempt after the guard. Unverified text is never kept."""

    status: str
    text: str | None = None
    reason: str | None = None
    asserted: tuple[int, ...] = ()

    @property
    def visible(self) -> bool:
        return self.text is not None and self.status == GuardStatus.PASS


@dataclass(frozen=True, slots=True)
class CoverNoteResult:
    note: CoverNoteView
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass(frozen=True, slots=True)
class CoverWriter:
    llm: LLMClient
    session_factory: sessionmaker[Session]
    prompts_dir: Path
    model: str
    min_words: int = 60
    max_words: int = 150

    async def write(
        self,
        *,
        structure: JdStructure | None,
        results: Sequence[RequirementResult],
        cv_text: str,
        jd_text: str,
        section_texts: dict[str, str] | None = None,
    ) -> CoverNoteResult:
        claims = _claims(results)
        if not claims:
            return CoverNoteResult(
                note=CoverNoteView(
                    status=NO_STRONG_MATCHES,
                    reason="No requirement had verified evidence to assert.",
                )
            )
        prompt, user, context = self._prepare(
            claims=claims,
            structure=structure,
            results=results,
            cv_text=cv_text,
            jd_text=jd_text,
            section_texts=section_texts,
        )
        first, tokens_in, tokens_out = await self._attempt(prompt, user, context)
        if first.visible:
            return CoverNoteResult(note=first, tokens_in=tokens_in, tokens_out=tokens_out)
        retry_user = f"{user}\n{VIOLATION_BLOCK.format(detail=first.reason or 'unknown')}"
        second, retry_in, retry_out = await self._attempt(prompt, retry_user, context)
        return CoverNoteResult(
            note=second,
            tokens_in=tokens_in + retry_in,
            tokens_out=tokens_out + retry_out,
        )

    def _prepare(
        self,
        *,
        claims: Sequence[CoverClaim],
        structure: JdStructure | None,
        results: Sequence[RequirementResult],
        cv_text: str,
        jd_text: str,
        section_texts: dict[str, str] | None,
    ) -> tuple[PromptText, str, CoverContext]:
        context = _context(
            claims=claims,
            results=results,
            cv_text=cv_text,
            section_texts=section_texts,
            structure=structure,
            min_words=self.min_words,
            max_words=self.max_words,
        )
        prompt = load_prompt(self.prompts_dir, PROMPT_NAME)
        user = fill(
            prompt.user_template,
            {
                "confirmed_matches": _confirmed(claims),
                "cv_text": cv_text,
                "jd_text": jd_text,
            },
        )
        return prompt, user, context

    async def _attempt(
        self, prompt: PromptText, user: str, context: CoverContext
    ) -> tuple[CoverNoteView, int, int]:
        request = LlmRequest(
            step=Step.S7_COVER_NOTE,
            prompt_version=prompt.ref.prompt_version,
            system=prompt.system,
            user=user,
            schema_name=SCHEMA_NAME,
        )
        try:
            response = await self.llm.complete(request)
        except LLMError as exc:
            self._record(request, LlmOutcome.ERROR)
            raise AppError(exc.code, str(exc), {"step": request.step}) from exc
        try:
            draft = cast(CoverNoteDraft, load_payload(SCHEMA_NAME, response.payload))
        except ValidationError as exc:
            self._record(request, LlmOutcome.INVALID)
            raise AppError(
                "LLM_SCHEMA_INVALID",
                "The model returned a result that does not match the schema.",
                {"step": request.step},
            ) from exc
        self._record(request, LlmOutcome.OK, response)
        result = check_cover_note(draft, context)
        view = CoverNoteView(
            status=result.status,
            text=draft.text if result.ok else None,
            reason=result.detail,
            asserted=tuple(sorted(set(draft.asserted_requirement_indexes))),
        )
        return view, response.tokens_in, response.tokens_out

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


def word_count(text: str | None) -> int:
    return len((text or "").split())


def _claims(results: Sequence[RequirementResult]) -> tuple[CoverClaim, ...]:
    """Strong verdicts with a quote, most important first, indexed from zero."""
    strong = [
        item
        for item in results
        if item.verdict == Verdict.STRONG and (item.evidence_quote or "").strip()
    ]
    ranked = sorted(
        strong,
        key=lambda item: (IMPORTANCE_ORDER.get(item.importance, 9), item.position),
    )
    return tuple(
        CoverClaim(
            index=index,
            requirement=item.text,
            quote=(item.evidence_quote or "").strip(),
        )
        for index, item in enumerate(ranked)
    )


def _confirmed(claims: Sequence[CoverClaim]) -> str:
    return "\n".join(
        f'{claim.index}) {claim.requirement}\n   quote: "{claim.quote}"' for claim in claims
    )


def _open_keywords(results: Sequence[RequirementResult]) -> frozenset[str]:
    """Keywords of requirements the CV does not fully meet."""
    found: set[str] = set()
    for item in results:
        if item.verdict == Verdict.STRONG:
            continue
        for keyword in item.keywords:
            cleaned = keyword.strip().casefold()
            if len(cleaned) >= MIN_KEYWORD_LENGTH:
                found.add(cleaned)
    return frozenset(found)


def _reserved(structure: JdStructure | None) -> frozenset[str]:
    """The role and the company may be named even when the CV never says them."""
    if structure is None:
        return frozenset()
    parts = [part for part in (structure.title, structure.company) if part]
    return frozenset(words(" ".join(parts)))


def _context(
    *,
    claims: Sequence[CoverClaim],
    results: Sequence[RequirementResult],
    cv_text: str,
    section_texts: dict[str, str] | None,
    structure: JdStructure | None,
    min_words: int,
    max_words: int,
) -> CoverContext:
    return CoverContext(
        guard=GuardContext.build(cv_text=cv_text, section_texts=section_texts),
        strong=tuple(claims),
        open_keywords=_open_keywords(results),
        reserved=_reserved(structure),
        min_words=min_words,
        max_words=max_words,
    )
