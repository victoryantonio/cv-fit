"""Implements `JobAlertSource` by talking to the `mcp_gmail` helper over stdio.

One process per call: a sync is two calls, so nothing long-lived is left behind
and a crashed helper cannot wedge the API. The helper holds the Gmail
credential; this process never sees it, and never contacts Gmail itself.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.modules.jobs.ports import AlertCard, AlertDetail, AlertMessage, AlertSourceError

LIST_TOOL: Final = "list_job_alerts"
GET_TOOL: Final = "get_job_alert"

#: A bare interpreter is resolved to this one, so the helper runs in the same
#: environment as the backend even when `python` on PATH is a different install.
_INTERPRETERS: Final[frozenset[str]] = frozenset({"python", "python3", "py"})


@dataclass(frozen=True, slots=True)
class McpJobAlertSource:
    command: str
    timeout_seconds: float = 60.0
    extra_env: Mapping[str, str] = field(default_factory=dict)

    async def list_alerts(
        self, *, since: datetime | None = None, limit: int = 25
    ) -> list[AlertMessage]:
        payload = await self._call(
            LIST_TOOL,
            {"since": since.isoformat() if since is not None else None, "limit": limit},
        )
        messages = payload.get("messages")
        if not isinstance(messages, list):
            raise AlertSourceError("The Gmail helper returned no message list.")
        return [
            AlertMessage(
                message_id=str(item["message_id"]),
                received_at=_parse_moment(item.get("received_at")),
            )
            for item in messages
            if isinstance(item, dict) and item.get("message_id")
        ]

    async def fetch_alert(self, message_id: str) -> AlertDetail:
        payload = await self._call(GET_TOOL, {"message_id": message_id})
        cards = payload.get("cards")
        if not isinstance(cards, list):
            raise AlertSourceError("The Gmail helper returned no card list.")
        return AlertDetail(
            message_id=str(payload.get("message_id") or message_id),
            received_at=_parse_moment(payload.get("received_at")),
            cards=[
                AlertCard(
                    title=str(card.get("title") or ""),
                    company=_text(card.get("company")),
                    location=_text(card.get("location")),
                    url=_text(card.get("url")),
                )
                for card in cards
                if isinstance(card, dict)
            ],
            warnings=[str(warning) for warning in payload.get("warnings") or []],
        )

    def _parameters(self) -> StdioServerParameters:
        # posix=False on Windows keeps backslashes in paths; posix rules would
        # eat them and the interpreter would not be found.
        tokens = shlex.split(self.command, posix=os.name != "nt")
        if not tokens:
            raise AlertSourceError("GMAIL_MCP_COMMAND is empty.")
        executable = sys.executable if tokens[0] in _INTERPRETERS else tokens[0]
        # Inherit the real environment: mcp's own `get_default_environment()` is a
        # small allowlist, and on Windows a child without SystemRoot cannot start.
        return StdioServerParameters(
            command=executable,
            args=tokens[1:],
            env={**os.environ, **self.extra_env},
        )

    async def _call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            return await asyncio.wait_for(self._session_call(tool, arguments), self.timeout_seconds)
        except TimeoutError as exc:
            raise AlertSourceError(
                "The Gmail helper did not answer in time.", code="GMAIL_NOT_CONNECTED"
            ) from exc

    async def _session_call(self, tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
        try:
            async with (
                stdio_client(self._parameters()) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                result = await session.call_tool(tool, arguments)
        except AlertSourceError:
            raise
        except Exception as exc:  # noqa: BLE001 - every transport failure means "unreachable"
            raise AlertSourceError(
                "The Gmail helper could not be started.", code="GMAIL_NOT_CONNECTED"
            ) from exc
        if getattr(result, "isError", False):
            # The tools report failures as an `error` envelope; a raised tool is a
            # broken helper, which is what reconnecting fixes.
            raise AlertSourceError("The Gmail helper failed.", code="GMAIL_NOT_CONNECTED")
        payload = _payload(result)
        error = payload.get("error")
        if isinstance(error, dict):
            raise AlertSourceError(
                str(error.get("message") or "The Gmail helper failed."),
                code=str(error.get("code") or "ALERT_PARSE_FAILED"),
            )
        return payload


def _payload(result: Any) -> dict[str, Any]:
    """Prefer structured content; fall back to JSON in a text block."""
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        return structured
    for block in getattr(result, "content", []) or []:
        text = getattr(block, "text", None)
        if text:
            try:
                decoded = json.loads(text)
            except ValueError:
                continue
            if isinstance(decoded, dict):
                return decoded
    raise AlertSourceError("The Gmail helper returned something this app cannot read.")


def _text(value: Any) -> str | None:
    return str(value) if value else None


def _parse_moment(value: Any) -> datetime:
    """Alert dates arrive as ISO strings; a naive value is treated as UTC."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(UTC)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.now(UTC)
