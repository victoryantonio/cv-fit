"""S1: turn pasted text into a structured, quote-backed requirement list.

The model never invents requirements that survive: every item must carry a quote
that is a literal substring of the pasted text, or the item is dropped and
counted. Refusals (not a job post, several jobs) are persisted so a second call
does not pay for the same refusal twice.

The acceptance rules themselves are pure and live in `structure_rules`; this
module only does the prompt, the call, the cache and the write.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.modules.analysis.call_ledger import record_call
from app.modules.analysis.enums import ExtractionStatus, LlmOutcome, Step
from app.modules.analysis.models import JdExtraction, JdRequirement
from app.modules.analysis.ports import LLMClient, LLMError, LlmRequest, LlmResponse
from app.modules.analysis.prompts import fill, load_prompt
from app.modules.analysis.schemas import JdStructure, load_payload
from app.modules.analysis.structure_rules import Prepared, prepared, requirement_models
from app.modules.analysis.views import RequirementView, StructuredJd, extraction_key
from app.shared.clock import Clock
from app.shared.errors import AppError

PROMPT_NAME: Final = "jd_structure"
# v2 adds the navigation rule (job_count) and excludes the hiring sentence.
PROMPT_VERSION: Final = "v2"
SCHEMA_NAME: Final = "jd_structure"


def _requirement_rows(session: Session, extraction_id: str) -> list[RequirementView]:
    statement = (
        select(JdRequirement)
        .where(JdRequirement.extraction_id == extraction_id, JdRequirement.active.is_(True))
        .order_by(JdRequirement.position)
    )
    return [
        RequirementView(
            id=row.id,
            position=row.position,
            text=row.text,
            category=row.category,
            importance=row.importance,
            keywords=list(row.keywords or []),
            jd_quote=row.jd_quote,
        )
        for row in session.scalars(statement)
    ]


@dataclass(frozen=True, slots=True)
class JdStructurer:
    """S1 as a value: everything it needs is injected, so tests need no globals."""

    llm: LLMClient
    session_factory: sessionmaker[Session]
    prompts_dir: Path
    model: str
    clock: Clock

    async def run(self, *, snapshot_id: str, raw_text: str, text_sha256: str) -> StructuredJd:
        prompt = load_prompt(self.prompts_dir, PROMPT_NAME, PROMPT_VERSION)
        key = extraction_key(
            text_sha256=text_sha256, prompt_bundle=prompt.ref.bundle, model=self.model
        )
        cached = self._cached(key)
        if cached is not None:
            return cached
        request = LlmRequest(
            step=Step.S1_EXTRACT,
            prompt_version=prompt.ref.prompt_version,
            system=prompt.system,
            user=fill(prompt.user_template, {"jd_text": raw_text}),
            schema_name=SCHEMA_NAME,
        )
        return await self._extract(
            snapshot_id=snapshot_id,
            raw_text=raw_text,
            key=key,
            bundle=prompt.ref.bundle,
            request=request,
        )

    def _cached(self, key: str) -> StructuredJd | None:
        with self.session_factory() as session:
            extraction = session.scalars(
                select(JdExtraction).where(JdExtraction.extract_key == key)
            ).first()
            if extraction is None:
                return None
            structure = (
                JdStructure.model_validate(extraction.structured) if extraction.structured else None
            )
            result = StructuredJd(
                extraction_id=extraction.id,
                snapshot_id=extraction.jd_snapshot_id,
                status=extraction.status,
                structure=structure,
                requirements=_requirement_rows(session, extraction.id),
                cache_hit=True,
            )
        self._raise_for_status(result.status)
        return result

    async def _extract(
        self,
        *,
        snapshot_id: str,
        raw_text: str,
        key: str,
        bundle: str,
        request: LlmRequest,
    ) -> StructuredJd:
        try:
            response = await self.llm.complete(request)
        except LLMError as exc:
            self._record_failure(request)
            raise AppError(exc.code, str(exc), {"step": request.step}) from exc
        try:
            structure = cast(JdStructure, load_payload(SCHEMA_NAME, response.payload))
        except ValidationError as exc:
            self._record_failure(request)
            raise AppError(
                "LLM_SCHEMA_INVALID",
                "The model returned a result that does not match the schema.",
                {"step": request.step},
            ) from exc
        result = self._persist(
            snapshot_id=snapshot_id,
            raw_text=raw_text,
            key=key,
            bundle=bundle,
            structure=structure,
            response=response,
            request=request,
        )
        self._raise_for_status(result.status)
        return result

    def _record_failure(self, request: LlmRequest) -> None:
        with self.session_factory() as session:
            record_call(session, request=request, model=self.model, outcome=LlmOutcome.ERROR)
            session.commit()

    def _persist(
        self,
        *,
        snapshot_id: str,
        raw_text: str,
        key: str,
        bundle: str,
        structure: JdStructure,
        response: LlmResponse,
        request: LlmRequest,
    ) -> StructuredJd:
        acceptance = prepared(structure, raw_text)
        extraction_id, views = self._store(
            snapshot_id=snapshot_id,
            key=key,
            bundle=bundle,
            structure=structure,
            acceptance=acceptance,
            response=response,
            request=request,
        )
        return StructuredJd(
            extraction_id=extraction_id,
            snapshot_id=snapshot_id,
            status=acceptance.status,
            structure=structure,
            requirements=views,
            dropped_quotes=acceptance.dropped,
            duplicates=acceptance.duplicates,
            warnings=list(acceptance.warnings),
            tokens_in=response.tokens_in,
            tokens_out=response.tokens_out,
        )

    def _store(
        self,
        *,
        snapshot_id: str,
        key: str,
        bundle: str,
        structure: JdStructure,
        acceptance: Prepared,
        response: LlmResponse,
        request: LlmRequest,
    ) -> tuple[str, list[RequirementView]]:
        with self.session_factory() as session:
            extraction = JdExtraction(
                jd_snapshot_id=snapshot_id,
                extract_key=key,
                model=self.model,
                prompt_bundle=bundle,
                structured=structure.model_dump(mode="json"),
                status=acceptance.status,
                created_at=self.clock.now(),
            )
            session.add(extraction)
            session.flush()
            session.add_all(requirement_models(extraction.id, acceptance.requirements))
            record_call(
                session,
                request=request,
                model=self.model,
                outcome=LlmOutcome.OK,
                tokens_in=response.tokens_in,
                tokens_out=response.tokens_out,
                latency_ms=response.latency_ms,
            )
            session.commit()
            return extraction.id, _requirement_rows(session, extraction.id)

    @staticmethod
    def _raise_for_status(status: str) -> None:
        if status == ExtractionStatus.JD_NOT_FOUND:
            raise AppError(
                "JD_NOT_FOUND",
                "That text does not read as a job post. Paste the advert itself.",
            )
        if status == ExtractionStatus.JD_MULTIPLE_JOBS:
            raise AppError(
                "JD_MULTIPLE_JOBS",
                "That text contains more than one job. Paste a single advert.",
            )
