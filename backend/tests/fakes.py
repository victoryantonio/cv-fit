"""Scripted LLM double. Returns validated objects and fails on cue."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import Any

from pydantic import BaseModel, ValidationError

from app.modules.analysis.ports import LLMError, LlmRequest, LlmResponse
from app.modules.analysis.schemas import load_payload
from app.modules.cvs.parser import DocumentParseError, ParsedCv

Payload = BaseModel | dict[str, Any] | Exception


class FakeDocumentParser:
    """Honors the DocumentParser contract without spawning a subprocess."""

    def __init__(self, parsed: ParsedCv | None = None, error: str | None = None) -> None:
        self.parsed = parsed
        self.error = error
        self.calls: list[str] = []

    def parse(self, data: bytes, *, file_name: str) -> ParsedCv:
        self.calls.append(file_name)
        if self.error is not None:
            raise DocumentParseError(self.error)
        assert self.parsed is not None, "FakeDocumentParser needs a parsed result or an error"
        return self.parsed


class FakeLLMClient:
    """Answers in order. Any scripted Exception is raised as an LLMError.

    The fake honors the real contract: it validates payloads against the same
    schema the real client does, and it raises LLMError, not RuntimeError.
    `defaults` answers a whole schema the test does not care about, so a script
    can describe only the step under test without running out of answers.
    """

    def __init__(
        self, script: Iterable[Payload] | None = None, defaults: dict[str, Payload] | None = None
    ) -> None:
        self._script: Iterator[Payload] = iter(script or [])
        self._defaults = dict(defaults or {})
        self.requests: list[LlmRequest] = []
        self._repeater: Payload | None = None

    def queue(self, *payloads: Payload) -> FakeLLMClient:
        self._script = iter(list(self._script) + list(payloads))
        return self

    def repeat(self, payload: Payload) -> FakeLLMClient:
        """Answer every remaining call with the same payload."""
        self._repeater = payload
        return self

    async def reachable(self) -> bool:
        """Health asks this; a scripted fake stands in for a configured provider."""
        return True

    async def complete(self, request: LlmRequest) -> LlmResponse:
        self.requests.append(request)
        payload = next(self._script, None)
        if payload is None:
            payload = self._defaults.get(request.schema_name)
        if payload is None:
            payload = self._repeater
        if payload is None:
            raise LLMError("fake LLM ran out of scripted answers", code="LLM_SCRIPT_EMPTY")
        if isinstance(payload, Exception):
            raise payload if isinstance(payload, LLMError) else LLMError(str(payload))
        raw = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        try:
            load_payload(request.schema_name, raw)
        except ValidationError as exc:
            raise LLMError(
                f"scripted payload violates {request.schema_name}", code="LLM_INVALID"
            ) from exc
        return LlmResponse(
            payload=raw,
            tokens_in=len(request.user) // 4,
            tokens_out=len(str(raw)) // 4,
            latency_ms=1,
        )
