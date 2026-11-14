"""The only place that talks to the model provider.

OpenAI-compatible endpoint, JSON response mode, Pydantic validation, repair
retries, and one mapping from provider exceptions to the stable error codes in
PRD §8.11. Prompt text and model output are never logged.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable, Sequence
from time import perf_counter
from typing import Any, Final

import httpx
import openai
from pydantic import ValidationError

from app.modules.analysis.ports import LLMError, LlmRequest, LlmResponse
from app.modules.analysis.schemas import load_payload, render_schema
from app.shared.llm_config import LlmRuntime

MAX_TEMPERATURE: Final = 0.2
DEFAULT_TIMEOUT_SECONDS: Final = 60.0
MAX_REPAIR_RETRIES: Final = 2
# Health polls this; a provider that hangs must not hold the request open.
PROBE_TIMEOUT_SECONDS: Final = 5.0
# PRD §8.11: retry a slow or rate-limited provider three times before failing.
DEFAULT_BACKOFF_SECONDS: Final[tuple[float, ...]] = (2.0, 8.0, 30.0)

SCHEMA_PREAMBLE: Final = (
    "Return one JSON object that validates against the JSON Schema below. Use exactly "
    "these keys: unknown keys and missing required keys both fail validation.\n\n"
)

REPAIR_INSTRUCTION: Final = (
    "The previous answer did not validate against the schema above. Return only JSON "
    "that matches it, with no prose and no code fences."
)


def schema_contract(name: str) -> str:
    """The schema text that travels with the request.

    The provider has no strict structured-output mode (`json_schema` is rejected),
    so the contract has to be stated in the prompt. Rendering it from the same
    Pydantic model that validates the reply is what keeps the two from drifting.
    """
    return SCHEMA_PREAMBLE + render_schema(name)


Sleep = Callable[[float], Awaitable[None]]


def _map_provider_error(exc: Exception) -> LLMError:
    if isinstance(exc, openai.AuthenticationError | openai.PermissionDeniedError):
        return LLMError("The model provider rejected the credentials.", code="LLM_AUTH")
    if isinstance(exc, openai.RateLimitError):
        return LLMError("The model provider is rate limiting.", code="LLM_RATE_LIMIT")
    if isinstance(exc, openai.APITimeoutError | httpx.TimeoutException):
        return LLMError("The model provider timed out.", code="LLM_TIMEOUT")
    if isinstance(exc, openai.APIConnectionError | httpx.TransportError):
        return LLMError("The model provider is unreachable.", code="LLM_UNAVAILABLE")
    if isinstance(exc, openai.APIStatusError):
        code = "LLM_UNAVAILABLE" if exc.status_code >= 500 else "LLM_ERROR"
        # The status is the only clue a failed run leaves behind: the two eval runs
        # that died on this path both reported the same sentence, so which rejection
        # the provider sent was unknowable after the fact.
        return LLMError(
            f"The model provider returned HTTP {exc.status_code}.",
            code=code,
        )
    return LLMError("The model call failed.", code="LLM_ERROR")


def _is_retryable(error: LLMError) -> bool:
    return error.code in {"LLM_TIMEOUT", "LLM_RATE_LIMIT", "LLM_UNAVAILABLE"}


def _strip_fences(content: str) -> str:
    """`json_object` mode usually suffices, but fences still appear in practice."""
    text = content.strip()
    if not text.startswith("```"):
        return text
    _, _, remainder = text.partition("\n")
    return remainder.rsplit("```", 1)[0].strip()


def _decode(schema_name: str, content: str) -> dict[str, Any]:
    """Parse and validate in one place, so a repair retry cannot skip the schema."""
    payload = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("the response is not a JSON object")
    load_payload(schema_name, payload)
    return payload


class OpenAiLLMClient:
    """Honors the LLMClient protocol. Configuration is read per call, not cached."""

    def __init__(
        self,
        config: Callable[[], LlmRuntime],
        *,
        client_factory: Callable[[LlmRuntime], Any] | None = None,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_repair_retries: int = MAX_REPAIR_RETRIES,
        backoff_seconds: Sequence[float] = DEFAULT_BACKOFF_SECONDS,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._config = config
        self._client_factory = client_factory or self._default_client
        self._timeout_seconds = timeout_seconds
        self._max_repair_retries = max_repair_retries
        self._backoff_seconds = tuple(backoff_seconds)
        self._sleep = sleep

    def _default_client(self, config: LlmRuntime) -> openai.AsyncOpenAI:
        return openai.AsyncOpenAI(
            base_url=config.base_url,
            api_key=config.api_key or "missing",
            timeout=self._timeout_seconds,
            max_retries=0,  # this client owns the retry policy
        )

    async def complete(self, request: LlmRequest) -> LlmResponse:
        config = self._config()
        if not config.api_key:
            raise LLMError("No API key is configured for the model provider.", code="LLM_AUTH")
        client = self._client_factory(config)
        system = f"{request.system}\n\n{schema_contract(request.schema_name)}"
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": request.user},
        ]
        return await self._call(client, config, request, messages)

    async def reachable(self) -> bool:
        """True when the provider answers, False when no key is configured.

        Health needs the answer without spending tokens, so this asks for the
        cheapest endpoint the provider exposes and gives up quickly: a frozen
        provider must not hold the health endpoint open for a full completion
        timeout. Failures raise LLMError like any other call, which keeps a
        rejected key distinguishable from a dead host.
        """
        config = self._config()
        if not config.api_key:
            return False
        client = self._client_factory(config)
        try:
            await client.models.list(timeout=PROBE_TIMEOUT_SECONDS)
        except Exception as exc:  # provider SDK raises a wide family of types
            raise _map_provider_error(exc) from exc
        return True

    async def _send(
        self,
        client: Any,
        config: LlmRuntime,
        request: LlmRequest,
        messages: list[dict[str, str]],
    ) -> tuple[Any, int]:
        """One request with transport retries. Returns (response, latency in ms)."""
        failures = 0
        while True:
            started = perf_counter()
            try:
                response = await client.chat.completions.create(
                    model=config.model,
                    messages=messages,
                    temperature=min(request.temperature, MAX_TEMPERATURE),
                    response_format={"type": "json_object"},
                )
            except Exception as exc:  # provider SDK raises a wide family of types
                error = _map_provider_error(exc)
                if _is_retryable(error) and failures < len(self._backoff_seconds):
                    await self._sleep(self._backoff_seconds[failures])
                    failures += 1
                    continue
                raise error from exc
            return response, int((perf_counter() - started) * 1000)

    async def _call(
        self,
        client: Any,
        config: LlmRuntime,
        request: LlmRequest,
        messages: list[dict[str, str]],
    ) -> LlmResponse:
        repairs = 0
        while True:
            response, latency_ms = await self._send(client, config, request, messages)
            content = _strip_fences(response.choices[0].message.content or "")
            try:
                payload = _decode(request.schema_name, content)
            except (json.JSONDecodeError, ValueError, ValidationError) as exc:
                if repairs >= self._max_repair_retries:
                    raise LLMError(
                        "The model returned a result that does not match the schema.",
                        code="LLM_SCHEMA_INVALID",
                    ) from exc
                repairs += 1
                messages = [
                    *messages,
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": REPAIR_INSTRUCTION},
                ]
                continue
            usage = response.usage
            return LlmResponse(
                payload=payload,
                tokens_in=int(getattr(usage, "prompt_tokens", 0) or 0),
                tokens_out=int(getattr(usage, "completion_tokens", 0) or 0),
                latency_ms=latency_ms,
            )
