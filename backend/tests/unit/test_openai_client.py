"""The provider client: JSON mode, repair retries, and one error mapping.

No network is touched: the SDK is replaced by a stub whose `create` answers from
a script, so the retry and validation logic is what gets exercised.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

from app.modules.analysis.openai_client import PROBE_TIMEOUT_SECONDS, OpenAiLLMClient
from app.modules.analysis.ports import LLMError, LlmRequest
from app.shared.llm_config import LlmRuntime

RUNTIME = LlmRuntime(base_url="http://127.0.0.1:9/v1", model="test-model", api_key="k")

VALID = {
    "is_job_post": True,
    "job_count": 1,
    "requirements": [
        {
            "text": "Strong SQL",
            "category": "skill",
            "importance": "weight",
            "keywords": ["SQL"],
            "jd_quote": "Strong SQL",
        }
    ],
}


def _response(content: str) -> Any:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=22),
    )


class _Completions:
    def __init__(self, script: Iterator[Any]) -> None:
        self._script = script
        self.calls: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        answer = next(self._script)
        if isinstance(answer, Exception):
            raise answer
        return _response(answer)


class _Sleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def _client(script: list[Any], sleep: _Sleep | None = None) -> tuple[OpenAiLLMClient, _Completions]:
    completions = _Completions(iter(script))
    client = OpenAiLLMClient(
        lambda: RUNTIME,
        client_factory=lambda _runtime: SimpleNamespace(
            chat=SimpleNamespace(completions=completions)
        ),
        backoff_seconds=(0.0, 0.0, 0.0),
        sleep=sleep or _Sleep(),
    )
    return client, completions


def _request() -> LlmRequest:
    return LlmRequest(
        step="s1_extract",
        prompt_version="jd_structure.v1",
        system="system",
        user="user",
        schema_name="jd_structure",
        temperature=0.9,
    )


async def test_valid_json_is_returned_with_usage() -> None:
    client, completions = _client([json.dumps(VALID)])
    result = await client.complete(_request())
    assert result.payload["job_count"] == 1
    assert (result.tokens_in, result.tokens_out) == (11, 22)
    assert completions.calls[0]["response_format"] == {"type": "json_object"}
    assert completions.calls[0]["temperature"] == 0.2  # clamped, never above 0.2


async def test_the_schema_travels_with_every_request() -> None:
    """Validation is enforced from the prompt: the model is never asked to guess it."""
    client, completions = _client([json.dumps(VALID)])
    await client.complete(_request())
    system = completions.calls[0]["messages"][0]
    assert system["role"] == "system"
    assert system["content"].startswith("system")  # the prompt text survives
    assert '"jd_quote"' in system["content"]  # and the contract is appended
    assert '"is_job_post"' in system["content"]
    assert "JSON Schema" in system["content"]


async def test_the_repair_attempt_still_carries_the_schema() -> None:
    client, completions = _client(["not json at all", json.dumps(VALID)])
    await client.complete(_request())
    for call in completions.calls:
        assert '"jd_quote"' in call["messages"][0]["content"]


async def test_code_fences_are_stripped() -> None:
    client, _ = _client(["```json\n" + json.dumps(VALID) + "\n```"])
    result = await client.complete(_request())
    assert result.payload["job_count"] == 1


async def test_invalid_answer_is_repaired_once() -> None:
    client, completions = _client(["not json at all", json.dumps(VALID)])
    result = await client.complete(_request())
    assert result.payload["job_count"] == 1
    assert len(completions.calls) == 2
    repair_messages = completions.calls[1]["messages"]
    assert repair_messages[-1]["role"] == "user"
    assert "Return only JSON" in repair_messages[-1]["content"]


async def test_schema_violation_is_repaired_then_fails_loudly() -> None:
    bad = json.dumps({"is_job_post": True, "job_count": 1, "requirements": []})
    client, completions = _client([bad, bad, bad])
    with pytest.raises(LLMError) as error:
        await client.complete(_request())
    assert error.value.code == "LLM_SCHEMA_INVALID"
    assert len(completions.calls) == 3


async def test_rate_limit_is_retried_before_failing() -> None:
    request = httpx.Request("POST", "http://127.0.0.1:9/v1")
    limited = openai.RateLimitError(
        "slow down", response=httpx.Response(429, request=request), body=None
    )
    sleep = _Sleep()
    client, completions = _client([limited, limited, limited, limited], sleep)
    with pytest.raises(LLMError) as error:
        await client.complete(_request())
    assert error.value.code == "LLM_RATE_LIMIT"
    assert len(completions.calls) == 4
    assert sleep.delays == [0.0, 0.0, 0.0]


async def test_auth_error_is_not_retried() -> None:
    request = httpx.Request("POST", "http://127.0.0.1:9/v1")
    denied = openai.AuthenticationError(
        "bad key", response=httpx.Response(401, request=request), body=None
    )
    client, completions = _client([denied])
    with pytest.raises(LLMError) as error:
        await client.complete(_request())
    assert error.value.code == "LLM_AUTH"
    assert len(completions.calls) == 1


async def test_missing_api_key_fails_before_any_call() -> None:
    client = OpenAiLLMClient(lambda: LlmRuntime(base_url="http://127.0.0.1:9/v1", model="m"))
    with pytest.raises(LLMError) as error:
        await client.complete(_request())
    assert error.value.code == "LLM_AUTH"


class _Models:
    def __init__(self, answer: Any) -> None:
        self._answer = answer
        self.calls: list[dict[str, Any]] = []

    async def list(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self._answer, Exception):
            raise self._answer
        return self._answer


def _probe_client(answer: Any) -> tuple[OpenAiLLMClient, _Models]:
    models = _Models(answer)
    client = OpenAiLLMClient(
        lambda: RUNTIME,
        client_factory=lambda _runtime: SimpleNamespace(models=models),
    )
    return client, models


async def test_reachable_asks_the_cheapest_endpoint_with_its_own_timeout() -> None:
    """A frozen provider must not hold the health endpoint for a full completion."""
    client, models = _probe_client(SimpleNamespace(data=[]))

    assert await client.reachable() is True
    assert models.calls == [{"timeout": PROBE_TIMEOUT_SECONDS}]


async def test_reachable_does_not_build_a_client_without_a_key() -> None:
    built: list[LlmRuntime] = []
    client = OpenAiLLMClient(
        lambda: LlmRuntime(base_url="http://127.0.0.1:9/v1", model="m"),
        client_factory=lambda runtime: built.append(runtime) or SimpleNamespace(),
    )

    assert await client.reachable() is False
    assert built == []


async def test_reachable_maps_a_rejected_key_to_auth() -> None:
    request = httpx.Request("GET", "http://127.0.0.1:9/v1/models")
    denied = openai.AuthenticationError(
        "bad key", response=httpx.Response(401, request=request), body=None
    )
    client, _ = _probe_client(denied)

    with pytest.raises(LLMError) as error:
        await client.reachable()
    assert error.value.code == "LLM_AUTH"


async def test_reachable_maps_a_dead_host_to_unavailable() -> None:
    request = httpx.Request("GET", "http://127.0.0.1:9/v1/models")
    client, _ = _probe_client(httpx.ConnectError("no route", request=request))

    with pytest.raises(LLMError) as error:
        await client.reachable()
    assert error.value.code == "LLM_UNAVAILABLE"
