"""The cache is keyed on content, not on rows: same text, same packet.

A hit must cost nothing, a miss must never be served the wrong packet, and a
forced re-run must not fork the analysis into two rows that disagree.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.container import Container, build_container
from app.modules.analysis.models import Analysis, LlmCall, RequirementMatch
from app.modules.cvs.parser import ParsedCv
from app.shared.clock import FixedClock
from tests.conftest import InMemorySecretStore
from tests.fakes import FakeLLMClient
from tests.fixtures.cover_notes import COVER_OK
from tests.fixtures.documents import build_docx
from tests.fixtures.jd_texts import CLEAN_PAGE, structure_payload
from tests.fixtures.matches import CV_TEXT, MATCH_SCRIPT

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "prompts"
MATCH_RUNS = 1
REQUIREMENT_COUNT = 5
SUGGEST_NONE: dict[str, Any] = {"suggestions": []}
SECOND_PAGE = CLEAN_PAGE + "\nYou will also own the on-call rotation for the payments API.\n"

Build = Callable[[list[object] | None], tuple[Container, FakeLLMClient]]


def _block() -> list[object]:
    """One pipeline run after the extraction: three judgment runs per requirement, S5, S7."""
    run: list[object] = [payload for payload in MATCH_SCRIPT for _ in range(MATCH_RUNS)]
    return [*run, SUGGEST_NONE, COVER_OK]


class SameTextParser:
    """Two uploads of the same words must hash to the same CV text."""

    def parse(self, data: bytes, *, file_name: str) -> ParsedCv:
        return ParsedCv(text=CV_TEXT, sections={"other": CV_TEXT}, warnings=[], kind="docx")


@pytest.fixture
def build(
    settings: Settings,
    schema: Engine,
    secret_store: InMemorySecretStore,
    clock: FixedClock,
) -> Build:
    configured = settings.model_copy(update={"prompts_dir": PROMPTS_DIR})

    def factory(script: list[object] | None = None) -> tuple[Container, FakeLLMClient]:
        llm = FakeLLMClient(
            script or [structure_payload(CLEAN_PAGE), *_block(), *_block()],
            defaults={"suggestion_batch": SUGGEST_NONE},
        )
        container = build_container(
            configured,
            engine=schema,
            secret_store=secret_store,
            clock=clock,
            llm_client=llm,
            document_parser=SameTextParser(),
        )
        return container, llm

    return factory


def _job(container: Container, text: str = CLEAN_PAGE) -> dict[str, Any]:
    job = container.jobs.create(title="Senior Backend Engineer")
    return container.jobs.add_snapshot(job["id"], raw_text=text, source_kind="page_paste")


def _version(container: Container, label: str = "one") -> str:
    cv = container.cvs.create(label=f"CV {label}")
    stored = container.cvs.add_version(cv["id"], file_name=f"{label}.docx", data=build_docx())
    return str(stored["id"])


async def test_the_same_packet_twice_runs_the_pipeline_once(build: Build) -> None:
    container, llm = build()
    snapshot = _job(container)
    version = _version(container)

    first = await container.analysis.run(cv_version_id=version, snapshot_id=snapshot["id"])
    calls = len(llm.requests)
    second = await container.analysis.run(cv_version_id=version, snapshot_id=snapshot["id"])

    assert second["cache_hit"] is True
    assert second["id"] == first["id"]
    assert len(llm.requests) == calls


async def test_the_same_text_in_another_cv_version_is_a_hit(build: Build) -> None:
    container, llm = build()
    snapshot = _job(container)
    first_version = _version(container, "one")
    second_version = _version(container, "two")

    first = await container.analysis.run(cv_version_id=first_version, snapshot_id=snapshot["id"])
    calls = len(llm.requests)
    second = await container.analysis.run(cv_version_id=second_version, snapshot_id=snapshot["id"])

    assert first_version != second_version
    assert second["cache_hit"] is True
    assert second["id"] == first["id"]
    assert len(llm.requests) == calls


async def test_one_added_line_in_the_job_post_is_a_miss(build: Build) -> None:
    script = [structure_payload(CLEAN_PAGE), *_block(), structure_payload(SECOND_PAGE), *_block()]
    container, llm = build(script)
    version = _version(container)
    first_page = _job(container)
    second_page = _job(container, SECOND_PAGE)

    first = await container.analysis.run(cv_version_id=version, snapshot_id=first_page["id"])
    calls = len(llm.requests)
    second = await container.analysis.run(cv_version_id=version, snapshot_id=second_page["id"])

    assert second["cache_hit"] is False
    assert second["id"] != first["id"]
    assert len(llm.requests) > calls


async def test_a_hit_is_visible_before_a_single_token_is_spent(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    container, llm = build()
    snapshot = _job(container)
    version = _version(container)
    empty = container.analysis.probe(cv_version_id=version, snapshot_id=snapshot["id"])

    first = await container.analysis.run(cv_version_id=version, snapshot_id=snapshot["id"])
    found = container.analysis.probe(cv_version_id=version, snapshot_id=snapshot["id"])

    assert empty["analysis_id"] is None
    assert found["cache_key"] == empty["cache_key"]
    assert found["analysis_id"] == first["id"]
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Analysis)) == 1
    assert len(llm.requests) == 1 + REQUIREMENT_COUNT * MATCH_RUNS + 2


async def test_a_forced_rerun_rewrites_the_same_analysis(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    container, llm = build()
    snapshot = _job(container)
    version = _version(container)
    first = await container.analysis.run(cv_version_id=version, snapshot_id=snapshot["id"])
    calls = len(llm.requests)

    again = await container.analysis.run(
        cv_version_id=version, snapshot_id=snapshot["id"], force=True
    )

    assert again["cache_hit"] is False
    assert again["id"] == first["id"]
    # The extraction is reused; every judgment run and both writers run again.
    assert len(llm.requests) == calls + REQUIREMENT_COUNT * MATCH_RUNS + 2
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Analysis)) == 1
        assert session.scalar(select(func.count()).select_from(RequirementMatch)) == (
            REQUIREMENT_COUNT
        )
        # Every real model call keeps its own row: those tokens were spent.
        assert session.scalar(select(func.count()).select_from(LlmCall)) == len(llm.requests)
