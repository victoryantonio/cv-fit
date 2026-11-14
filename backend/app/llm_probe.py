"""Health's view of the model provider.

It lives beside `llm_steps` for the same reason: it translates between two
modules that may not import each other (platform owns Health, analysis owns the
client), so the wiring layer owns the translation.

The probe answers one question honestly: can this tool call the model provider
right now, and if not, why. It never reports NOT_CONFIGURED while a key is
stored, which is what made a saved key look unset.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Protocol

from app.modules.analysis.ports import LLMError
from app.modules.platform.health import ProbeStatus
from app.shared.http import blocked_host_of
from app.shared.llm_config import LlmRuntime


class Reachable(Protocol):
    """The one method this probe needs from the LLM client."""

    async def reachable(self) -> bool: ...


class ProviderProbe:
    def __init__(
        self,
        *,
        client: Reachable,
        runtime: Callable[[], LlmRuntime],
        blocked_hosts: Sequence[str],
    ) -> None:
        self._client = client
        self._runtime = runtime
        self._blocked_hosts = tuple(blocked_hosts)

    async def probe(self) -> ProbeStatus:
        config = self._runtime()
        if not config.api_key:
            return ProbeStatus.NOT_CONFIGURED
        # base_url is user-editable, so the blocklist has to gate it: the rule is
        # that this backend never contacts those hosts, whatever the settings say.
        if blocked_host_of(config.base_url, blocked_hosts=self._blocked_hosts):
            return ProbeStatus.UNREACHABLE
        try:
            answered = await self._client.reachable()
        except LLMError as exc:
            # A rejected key needs a new key, not a retry, so it gets its own state.
            return ProbeStatus.AUTH_FAILED if exc.code == "LLM_AUTH" else ProbeStatus.UNREACHABLE
        return ProbeStatus.OK if answered else ProbeStatus.NOT_CONFIGURED
