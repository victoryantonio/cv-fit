"""Fixtures for the integration tests.

`build` hands back a container whose LLM and file parser are scripted and whose
every other boundary is real. It lives here so both analysis test modules get it
without importing a fixture by name.
"""

from __future__ import annotations

import pytest
from sqlalchemy.engine import Engine

from app.config import Settings
from app.container import Container, build_container
from app.shared.clock import FixedClock
from tests.conftest import InMemorySecretStore
from tests.fakes import FakeLLMClient
from tests.fixtures.jd_texts import CLEAN_PAGE, structure_payload
from tests.integration.analysis_build import (
    CV_ONE,
    CV_TWO,
    PROMPTS_DIR,
    SUGGEST_NONE,
    Build,
    NamedParser,
    per_run_script,
)


@pytest.fixture
def build(
    settings: Settings,
    schema: Engine,
    secret_store: InMemorySecretStore,
    clock: FixedClock,
) -> Build:
    """A container whose LLM and file parser are scripted, everything else is real."""
    configured = settings.model_copy(update={"prompts_dir": PROMPTS_DIR})

    def factory(script: list[object] | None = None) -> tuple[Container, FakeLLMClient]:
        llm = FakeLLMClient(
            script or [structure_payload(CLEAN_PAGE), *per_run_script()],
            defaults={"suggestion_batch": SUGGEST_NONE},
        )
        container = build_container(
            configured,
            engine=schema,
            secret_store=secret_store,
            clock=clock,
            llm_client=llm,
            document_parser=NamedParser({"one": CV_ONE, "two": CV_TWO}),
        )
        return container, llm

    return factory
