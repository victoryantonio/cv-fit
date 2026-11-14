"""Shared fixtures. Every test runs against a throwaway SQLite file."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.container import Container, build_container
from app.db import Base, create_db_engine, create_session_factory
from app.main import create_app

# Imported for the side effect of registering tables on Base.metadata.
from app.modules.analysis import models as _analysis_models  # noqa: F401
from app.modules.cvs import models as _cvs_models  # noqa: F401
from app.modules.jobs import models as _jobs_models  # noqa: F401
from app.modules.platform import models as _platform_models  # noqa: F401
from app.shared.clock import FixedClock


class InMemorySecretStore:
    """Honors the SecretStore protocol so tests never touch the OS keychain."""

    def __init__(self) -> None:
        self._values: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self._values.get(name)

    def set(self, name: str, value: str) -> None:
        self._values[name] = value

    def delete(self, name: str) -> None:
        self._values.pop(name, None)


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2025, 1, 2, 9, 0, tzinfo=UTC)


@pytest.fixture
def clock(fixed_now: datetime) -> FixedClock:
    return FixedClock(fixed_now)


@pytest.fixture
def secret_store() -> InMemorySecretStore:
    return InMemorySecretStore()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        data_dir=tmp_path / "data",
        prompts_dir=tmp_path / "prompts",
        # Never the real build: a checkout with `frontend/dist` present would
        # otherwise change what "/" returns depending on whether someone ran npm.
        ui_dist_dir=tmp_path / "dist",
        allowed_hosts=["127.0.0.1", "localhost", "testserver"],
        gmail_client_secret_path=None,
        # Pinned, not inherited. Pydantic still reads os.environ, so leaving this
        # alone made the whole suite pass or fail on whatever MATCH_RUNS the
        # caller's shell happened to export: the integration scripts queue one
        # verdict per requirement, and at the default of three the script ran out
        # mid-requirement and fed an S5 payload to the matcher. A fresh clone with
        # no exported variable got 26 failures for a reason no test file mentions.
        match_runs=1,
        # The background loop is a deployment concern; tests drive the worker by
        # hand so every step is asserted in the order it happens.
        worker_enabled=False,
    )


@pytest.fixture
def engine(settings: Settings) -> Iterator[Engine]:
    engine = create_db_engine(settings.database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def schema(engine: Engine) -> Engine:
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session_factory(schema: Engine) -> sessionmaker[Session]:
    return create_session_factory(schema)


@pytest.fixture
def container(
    settings: Settings,
    schema: Engine,
    secret_store: InMemorySecretStore,
    clock: FixedClock,
) -> Container:
    return build_container(settings, engine=schema, secret_store=secret_store, clock=clock)


@pytest.fixture
def client(container: Container) -> Iterator[TestClient]:
    with TestClient(create_app(container), base_url="http://127.0.0.1") as test_client:
        yield test_client


def drain(container: Container) -> None:
    """Run every queued task to a terminal status."""
    while asyncio.run(container.worker.run_once()) is not None:
        continue


def post_analysis(client: TestClient, container: Container, **payload: Any) -> dict[str, Any]:
    """POST /api/analyses, run the queue, and return the stored packet."""
    created = client.post("/api/analyses", json=payload)
    assert created.status_code == 202, created.text
    task_id = created.json()["task"]["id"]
    drain(container)
    task = client.get(f"/api/tasks/{task_id}").json()
    assert task["status"] == "ok", task
    read = client.get(f"/api/analyses/{task['analysis_id']}")
    assert read.status_code == 200, read.text
    return read.json()
