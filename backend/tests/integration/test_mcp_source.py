"""The backend's stdio adapter: spawn the helper, map payloads, map failures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client

from app.modules.jobs.mcp_source import McpJobAlertSource
from app.modules.jobs.ports import AlertSourceError

BACKEND_ROOT = Path(__file__).resolve().parents[2]
STUB = Path(__file__).resolve().parents[1] / "support" / "stub_alert_server.py"


def _source(*extra: str) -> McpJobAlertSource:
    return McpJobAlertSource(
        command=" ".join([sys.executable, str(STUB), *extra]),
        timeout_seconds=60.0,
        extra_env={"PYTHONPATH": str(BACKEND_ROOT)},
    )


@pytest.fixture
def source() -> McpJobAlertSource:
    return _source()


async def test_list_alerts_maps_ids_and_times(source: McpJobAlertSource) -> None:
    alerts = await source.list_alerts(limit=2)
    assert [alert.message_id for alert in alerts] == ["m1", "m2"]
    assert alerts[0].received_at.tzinfo is not None
    assert alerts[0].received_at.year == 2025


async def test_list_alerts_honors_the_limit(source: McpJobAlertSource) -> None:
    assert [alert.message_id for alert in await source.list_alerts(limit=1)] == ["m1"]


async def test_fetch_alert_maps_cards(source: McpJobAlertSource) -> None:
    detail = await source.fetch_alert("m1")
    assert detail.message_id == "m1"
    assert detail.warnings == []
    assert [card.title for card in detail.cards] == ["Senior AI Engineer", "AI Engineer"]
    first = detail.cards[0]
    assert (first.company, first.location) == ("Westpac", "Sydney, NSW")
    assert first.url is not None and first.url.endswith("/4453662232/")
    assert detail.cards[1].url is None


async def test_a_helper_error_envelope_becomes_an_alert_source_error(
    source: McpJobAlertSource,
) -> None:
    with pytest.raises(AlertSourceError) as caught:
        await source.fetch_alert("boom")
    assert caught.value.code == "ALERT_PARSE_FAILED"
    assert "unknown alert layout" in str(caught.value)


async def test_a_helper_error_keeps_its_own_code(source: McpJobAlertSource) -> None:
    with pytest.raises(AlertSourceError) as caught:
        await source.fetch_alert("missing")
    assert caught.value.code == "GMAIL_NOT_CONNECTED"


async def test_a_command_that_cannot_start_is_not_connected() -> None:
    source = McpJobAlertSource(command="", extra_env={})
    with pytest.raises(AlertSourceError) as caught:
        await source.list_alerts()
    assert caught.value.code == "GMAIL_NOT_CONNECTED"


async def test_a_short_timeout_is_reported_not_raised() -> None:
    source = McpJobAlertSource(
        command=f"{sys.executable} {STUB}",
        timeout_seconds=0.001,
        extra_env={"PYTHONPATH": str(BACKEND_ROOT)},
    )
    with pytest.raises(AlertSourceError) as caught:
        await source.list_alerts()
    assert caught.value.code == "GMAIL_NOT_CONNECTED"


async def test_the_real_helper_exposes_exactly_two_read_only_tools() -> None:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp_gmail"],
        env={**get_default_environment(), "PYTHONPATH": str(BACKEND_ROOT)},
    )
    async with (
        stdio_client(params) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.initialize()
        listed = await session.list_tools()
    assert sorted(tool.name for tool in listed.tools) == ["get_job_alert", "list_job_alerts"]
    for tool in listed.tools:
        assert tool.description


async def test_the_real_helper_without_credentials_answers_not_connected() -> None:
    source = McpJobAlertSource(
        command=f"{sys.executable} -m app.mcp_gmail",
        extra_env={
            "PYTHONPATH": str(BACKEND_ROOT),
            "GMAIL_CLIENT_SECRET_PATH": "",
        },
    )
    with pytest.raises(AlertSourceError) as caught:
        await source.list_alerts()
    assert caught.value.code == "GMAIL_NOT_CONNECTED"
    assert "GMAIL_CLIENT_SECRET_PATH" in str(caught.value)
