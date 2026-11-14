"""Health's model-provider probe: four states, and the blocklist still wins.

Before this existed, health answered NOT_CONFIGURED forever, so a key stored in
the keychain looked unset. These cases are the ones the user can actually hit.
"""

from __future__ import annotations

from app.llm_probe import ProviderProbe
from app.modules.analysis.ports import LLMError
from app.modules.platform.health import ProbeStatus
from app.shared.llm_config import LlmRuntime

RUNTIME = LlmRuntime(base_url="https://api.example.test/v1", model="m", api_key="k")
NO_KEY = LlmRuntime(base_url="https://api.example.test/v1", model="m")


class _Client:
    def __init__(self, *, answers: bool = True, error: Exception | None = None) -> None:
        self._answers = answers
        self._error = error
        self.calls = 0

    async def reachable(self) -> bool:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._answers


def _probe(
    client: _Client,
    *,
    runtime: LlmRuntime = RUNTIME,
    blocked_hosts: tuple[str, ...] = ("linkedin.com",),
) -> ProviderProbe:
    return ProviderProbe(client=client, runtime=lambda: runtime, blocked_hosts=blocked_hosts)


async def test_a_stored_key_with_an_answering_provider_is_ok() -> None:
    assert await _probe(_Client(answers=True)).probe() is ProbeStatus.OK


async def test_no_key_is_not_configured_without_asking_anyone() -> None:
    client = _Client()

    assert await _probe(client, runtime=NO_KEY).probe() is ProbeStatus.NOT_CONFIGURED
    assert client.calls == 0


async def test_a_client_that_answers_false_is_not_configured() -> None:
    assert await _probe(_Client(answers=False)).probe() is ProbeStatus.NOT_CONFIGURED


async def test_a_rejected_key_is_its_own_state() -> None:
    """A bad key needs a new key, not a retry, so it must not read as unreachable."""
    error = LLMError("denied", code="LLM_AUTH")

    assert await _probe(_Client(error=error)).probe() is ProbeStatus.AUTH_FAILED


async def test_a_dead_provider_is_unreachable() -> None:
    error = LLMError("down", code="LLM_UNAVAILABLE")

    assert await _probe(_Client(error=error)).probe() is ProbeStatus.UNREACHABLE


async def test_a_blocked_base_url_is_never_contacted() -> None:
    """base_url is user-editable, so the host blocklist has to gate the probe."""
    client = _Client()
    runtime = LlmRuntime(base_url="https://www.linkedin.com/jobs", model="m", api_key="k")

    assert await _probe(client, runtime=runtime).probe() is ProbeStatus.UNREACHABLE
    assert client.calls == 0
