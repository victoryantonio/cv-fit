"""A task's whole life: queued, running, and every way it can stop early.

E17 (retry), NFR-10 (budget) and the stale-task recovery all live in
`TaskService`, so these tests drive the real service against a real database and
assert the stored row, not the method's return value alone.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.container import Container, build_container
from app.modules.analysis.enums import Step, TaskStatus
from app.modules.analysis.models import AnalysisTask, LlmCall
from app.modules.analysis.service import PipelineCancelled
from app.modules.cvs.parser import ParsedCv
from app.shared.clock import FixedClock
from app.shared.errors import AppError
from tests.conftest import InMemorySecretStore, drain
from tests.fakes import FakeLLMClient
from tests.fixtures.cover_notes import COVER_OK
from tests.fixtures.documents import build_docx
from tests.fixtures.jd_texts import CLEAN_PAGE, structure_payload
from tests.fixtures.matches import CV_TEXT, MATCH_SCRIPT

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "prompts"
MATCH_RUNS = 1
REQUIREMENT_COUNT = 5
SUGGEST_NONE: dict[str, object] = {"suggestions": []}

Build = Callable[..., tuple[Container, FakeLLMClient]]


def _script(executions: int = 2) -> list[object]:
    """One analysis = extract, three judgment runs per requirement, S5, S7."""
    run: list[object] = [payload for payload in MATCH_SCRIPT for _ in range(MATCH_RUNS)]
    run.extend([SUGGEST_NONE, COVER_OK])
    return [structure_payload(CLEAN_PAGE), *[payload for _ in range(executions) for payload in run]]


class FixedParser:
    """The bytes are a real DOCX; the text is the one the quotes came from."""

    def parse(self, data: bytes, *, file_name: str) -> ParsedCv:
        return ParsedCv(text=CV_TEXT, sections={"other": CV_TEXT}, warnings=[], kind="docx")


@pytest.fixture
def build(
    settings: Settings,
    schema: Engine,
    secret_store: InMemorySecretStore,
    clock: FixedClock,
) -> Build:
    def factory(
        script: list[object] | None = None, **overrides: object
    ) -> tuple[Container, FakeLLMClient]:
        configured = settings.model_copy(update={"prompts_dir": PROMPTS_DIR, **overrides})
        llm = FakeLLMClient(script or _script(), defaults={"suggestion_batch": SUGGEST_NONE})
        container = build_container(
            configured,
            engine=schema,
            secret_store=secret_store,
            clock=clock,
            llm_client=llm,
            document_parser=FixedParser(),
        )
        return container, llm

    return factory


class Packet:
    """A CV version and a JD snapshot, the two ids a task needs."""

    def __init__(self, container: Container) -> None:
        cv = container.cvs.create(label="CV one")
        version = container.cvs.add_version(cv["id"], file_name="one.docx", data=build_docx())
        job = container.jobs.create(title="Senior Backend Engineer")
        snapshot = container.jobs.add_snapshot(
            job["id"], raw_text=CLEAN_PAGE, source_kind="page_paste"
        )
        self.container = container
        self.cv_version_id = str(version["id"])
        self.snapshot_id = str(snapshot["id"])

    def enqueue(self, **kwargs: object) -> dict[str, object]:
        found = self.container.tasks.enqueue(
            cv_version_id=self.cv_version_id,
            snapshot_id=self.snapshot_id,
            **kwargs,  # type: ignore[arg-type]
        )
        return found.as_dict()


def test_a_queued_task_runs_to_ok(build: Build) -> None:
    container, llm = build()
    packet = Packet(container)
    queued = packet.enqueue()

    assert queued["cache_hit"] is False
    task_id = str(queued["task_id"])
    before = container.tasks.get(task_id)
    assert before["status"] == TaskStatus.QUEUED
    assert before["attempts"] == 0
    assert before["current_step"] is None

    result = asyncio.run(container.worker.run_once())

    assert result is not None
    assert result["status"] == TaskStatus.OK
    assert result["current_step"] == Step.S9_PERSIST
    assert result["attempts"] == 1
    assert result["analysis_id"]
    assert result["started_at"] is not None
    assert result["finished_at"] is not None
    assert len(llm.requests) == 1 + REQUIREMENT_COUNT * MATCH_RUNS + 2


def test_an_empty_queue_leaves_the_worker_idle(build: Build) -> None:
    container, llm = build()

    assert asyncio.run(container.worker.run_once()) is None
    assert llm.requests == []


def test_a_cancelled_queued_task_never_reaches_the_model(build: Build) -> None:
    container, llm = build()
    packet = Packet(container)
    task_id = str(packet.enqueue()["task_id"])

    cancelled = container.tasks.cancel(task_id)

    assert cancelled["status"] == TaskStatus.CANCELLED
    assert cancelled["finished_at"] is not None
    assert asyncio.run(container.worker.run_once()) is None
    assert llm.requests == []
    assert container.tasks.get(task_id)["status"] == TaskStatus.CANCELLED


def test_a_cancel_between_steps_spends_nothing_more(build: Build) -> None:
    container, llm = build()
    packet = Packet(container)
    seen = {"count": 0}

    def stop() -> bool:
        seen["count"] += 1
        return seen["count"] > 2

    with pytest.raises(PipelineCancelled):
        asyncio.run(
            container.analysis.run(
                cv_version_id=packet.cv_version_id,
                snapshot_id=packet.snapshot_id,
                should_stop=stop,
            )
        )

    assert len(llm.requests) == 1
    assert (
        container.analysis.probe(
            cv_version_id=packet.cv_version_id, snapshot_id=packet.snapshot_id
        )["analysis_id"]
        is None
    )


def test_cancelling_a_running_task_waits_for_the_step_boundary(build: Build) -> None:
    container, _ = build()
    task_id = str(Packet(container).enqueue()["task_id"])

    container.tasks.start(task_id)
    asked = container.tasks.cancel(task_id)

    assert asked["status"] == TaskStatus.RUNNING
    assert asked["cancel_requested"] is True
    assert asked["finished_at"] is None
    assert container.tasks.cancel_pending(task_id) is True
    assert container.tasks.mark_cancelled(task_id)["status"] == TaskStatus.CANCELLED


def test_a_task_left_running_by_a_dead_process_is_queued_again(build: Build) -> None:
    container, _ = build()
    packet = Packet(container)
    task_id = str(packet.enqueue()["task_id"])
    container.tasks.start(task_id)

    recovered = container.tasks.recover_stale(0)

    assert recovered == 1
    after = container.tasks.get(task_id)
    assert after["status"] == TaskStatus.QUEUED
    assert after["error_code"] == "TASK_STALE"
    assert after["started_at"] is None
    assert asyncio.run(container.worker.run_once())["status"] == TaskStatus.OK


def test_a_failed_task_can_be_queued_again(build: Build) -> None:
    container, _ = build()
    packet = Packet(container)
    task_id = str(packet.enqueue()["task_id"])
    container.tasks.fail(task_id, code="LLM_AUTH")

    retried = container.tasks.retry(task_id)

    assert retried["status"] == TaskStatus.QUEUED
    assert retried["error_code"] is None
    assert retried["finished_at"] is None
    assert retried["started_at"] is None
    assert asyncio.run(container.worker.run_once())["status"] == TaskStatus.OK


def test_only_a_failed_or_cancelled_task_can_be_requeued(build: Build) -> None:
    container, _ = build()
    task_id = str(Packet(container).enqueue()["task_id"])

    with pytest.raises(AppError) as raised:
        container.tasks.retry(task_id)

    assert raised.value.code == "CONFLICT"


def test_a_spent_budget_blocks_new_work_until_it_is_overridden(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    container, _ = build(token_budget_monthly=100)
    packet = Packet(container)
    with session_factory() as session:
        session.add(
            LlmCall(
                step=Step.S2_MATCH,
                model="scripted",
                prompt_version="v1",
                tokens_in=80,
                tokens_out=40,
                latency_ms=10,
            )
        )
        session.commit()

    with pytest.raises(AppError) as raised:
        packet.enqueue()

    assert raised.value.code == "BUDGET_EXCEEDED"
    assert raised.value.details == {"limit": 100, "used": 120}
    assert str(packet.enqueue(override_budget=True)["task_id"])


def test_a_second_click_joins_the_task_already_waiting(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    container, _ = build()
    packet = Packet(container)

    first = packet.enqueue()
    second = packet.enqueue()

    assert second["cache_hit"] is False
    assert second["task_id"] == first["task_id"]
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AnalysisTask)) == 1


def test_a_stored_analysis_answers_without_a_task(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    container, llm = build()
    packet = Packet(container)
    drain(container)  # nothing queued: the worker must stay idle
    first = asyncio.run(
        container.analysis.run(cv_version_id=packet.cv_version_id, snapshot_id=packet.snapshot_id)
    )
    calls = len(llm.requests)

    found = packet.enqueue()

    assert found["cache_hit"] is True
    assert found["analysis_id"] == first["id"]
    assert found["task_id"] is None
    assert len(llm.requests) == calls
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(AnalysisTask)) == 0
