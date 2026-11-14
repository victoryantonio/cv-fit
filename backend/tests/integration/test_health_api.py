"""Health is the Stage A user interface, so it has to be honest."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from app.config import Settings
from app.container import Container, build_container
from app.main import create_app
from app.modules.platform.health import GMAIL_TOKEN_NAME, ProbeStatus
from app.shared.clock import Clock
from app.shared.secrets import SecretStore


class _CountingProbe:
    """Stands in for the provider so these tests stay offline."""

    def __init__(self, status: ProbeStatus) -> None:
        self._status = status
        self.calls = 0

    async def probe(self) -> ProbeStatus:
        self.calls += 1
        return self._status


def test_health_reports_the_providers_real_answer(
    settings: Settings,
    schema: Engine,
    secret_store: SecretStore,
    clock: Clock,
) -> None:
    """A key that works must read as ok; this is what the UI was never shown."""
    probe = _CountingProbe(ProbeStatus.OK)
    container = build_container(
        settings, engine=schema, secret_store=secret_store, clock=clock, llm_probe=probe
    )

    with TestClient(create_app(container), base_url="http://127.0.0.1") as client:
        assert client.get("/api/health").json()["llm"] == "ok"


def test_saving_settings_makes_health_ask_again(
    settings: Settings,
    schema: Engine,
    secret_store: SecretStore,
    clock: Clock,
) -> None:
    """The probe answer is cached; a new key must not hide behind a five minute TTL."""
    probe = _CountingProbe(ProbeStatus.NOT_CONFIGURED)
    container = build_container(
        settings, engine=schema, secret_store=secret_store, clock=clock, llm_probe=probe
    )

    with TestClient(create_app(container), base_url="http://127.0.0.1") as client:
        assert client.get("/api/health").json()["llm"] == "not_configured"
        assert probe.calls == 1

        body = client.get("/api/settings").json()
        body["llm"].pop("api_key_set", None)
        body["llm"]["api_key"] = "sk-test"
        assert client.put("/api/settings", json=body).status_code == 200

        client.get("/api/health")
        assert probe.calls == 2


def test_health_reports_ok_database(client: TestClient) -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"
    assert body["gmail"] == "not_connected"
    # No key is stored in this fixture, so the real probe answers without network.
    assert body["llm"] == "not_configured"
    assert set(body) == {"status", "database", "gmail", "llm", "checked_at"}
    assert response.headers["X-Request-ID"]


def test_gmail_turns_connected_when_a_token_exists(
    client: TestClient, container: Container
) -> None:
    container.secret_store.set(GMAIL_TOKEN_NAME, "token")

    assert client.get("/api/health").json()["gmail"] == "connected"


def test_the_connect_hand_off_names_the_auth_command(client: TestClient) -> None:
    """D1: the API never runs consent; it says which command to run."""
    response = client.post("/api/gmail/connect")

    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "GMAIL_NOT_CONNECTED"
    assert body["details"]["status"] == "not_connected"
    assert body["details"]["command"] == "uv run python -m app.mcp_gmail auth"
    assert "token" not in str(body["details"]).lower()


def test_the_connect_hand_off_is_quiet_once_a_token_exists(
    client: TestClient, container: Container
) -> None:
    container.secret_store.set(GMAIL_TOKEN_NAME, "token")

    body = client.post("/api/gmail/connect").json()
    assert body == {"status": "connected", "command": None}


def test_unknown_host_is_rejected(container: Container) -> None:
    with TestClient(create_app(container), base_url="http://evil.example") as client:
        response = client.get("/api/health")

    assert response.status_code == 400


def test_unexpected_error_returns_the_envelope(
    container: Container, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(container)

    async def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("secret CV text must not leak")

    monkeypatch.setattr(container.health, "check", boom)
    with TestClient(app, base_url="http://127.0.0.1", raise_server_exceptions=False) as client:
        response = client.get("/api/health")

    assert response.status_code == 500
    body = response.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["request_id"]
    assert "secret CV text" not in response.text
