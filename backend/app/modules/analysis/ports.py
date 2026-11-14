"""Ports the analysis pipeline depends on.

External systems are reached only through these Protocols, so every judgement
step can be tested with a scripted fake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from app.modules.analysis.schemas import (
    CoverNoteDraft,
    JdStructure,
    MatchVerdict,
    SuggestionBatch,
)


class LLMError(Exception):
    """The provider failed, timed out, or returned output that failed validation."""

    def __init__(self, message: str, *, code: str = "LLM_ERROR") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LlmRequest:
    """One call. `system` and `user` are already redacted by the caller."""

    step: str
    prompt_version: str
    system: str
    user: str
    schema_name: str
    temperature: float = 0.2


@dataclass(frozen=True)
class LlmResponse:
    payload: dict[str, Any]
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    cache_hit: bool = False


class LLMClient(Protocol):
    async def complete(self, request: LlmRequest) -> LlmResponse: ...

    async def reachable(self) -> bool:
        """Whether the provider answers, without spending a completion.

        Health needs this and cannot ask the client a private question, so it is
        part of the port: False means "no key stored", an LLMError means the
        provider was tried and failed.
        """
        ...


@dataclass(frozen=True)
class AlertEmail:
    message_id: str
    subject: str
    body: str
    received_at: str
    sender: str = ""


class JobAlertSource(Protocol):
    async def fetch_alerts(self, *, query: str, limit: int) -> list[AlertEmail]: ...


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    warnings: list[str] = field(default_factory=list)


class FileParser(Protocol):
    def parse(self, path: Path) -> ParsedDocument: ...


# Typed convenience aliases: the pipeline reads the schema from the request but
# always validates against these models, so a fake cannot drift from the contract.
JdStructureResponse = JdStructure
MatchVerdictResponse = MatchVerdict
SuggestionBatchResponse = SuggestionBatch
CoverNoteResponse = CoverNoteDraft
