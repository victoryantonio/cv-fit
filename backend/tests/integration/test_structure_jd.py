"""S1: is this a job post, and which requirements are actually quoted?

The fakes return scripted payloads, but every quote check is the real one: an
item survives only if its `jd_quote` is a literal substring of the pasted text.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.container import build_container
from app.modules.analysis.models import JdExtraction, JdRequirement
from app.modules.analysis.ports import LLMError
from app.modules.analysis.steps import JdStructurer
from app.modules.jobs.service import JobService
from app.shared.clock import FixedClock
from app.shared.errors import AppError
from tests.conftest import InMemorySecretStore
from tests.fakes import FakeLLMClient
from tests.fixtures.jd_texts import (
    CLEAN_PAGE,
    MULTI_JOB_PAGE,
    NOISY_PAGE,
    NON_JOB_TEXT,
    structure_payload,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "prompts"

Build = Callable[[list[object]], tuple[JdStructurer, FakeLLMClient, JobService]]


@pytest.fixture
def build(settings: Settings, schema: Engine, clock: FixedClock) -> Build:
    """A structurer bound to a scripted fake, all sharing one throwaway database."""

    def factory(script: list[object]) -> tuple[JdStructurer, FakeLLMClient, JobService]:
        llm = FakeLLMClient(script)  # type: ignore[arg-type]
        container = build_container(
            settings,
            engine=schema,
            secret_store=InMemorySecretStore(),
            clock=clock,
            llm_client=llm,
        )
        structurer = JdStructurer(
            llm=llm,
            session_factory=container.session_factory,
            prompts_dir=PROMPTS_DIR,
            model=settings.llm_model,
            clock=clock,
        )
        jobs = JobService(session_factory=container.session_factory, clock=clock)
        return structurer, llm, jobs

    return factory


def _prepare(jobs: JobService, raw_text: str) -> dict[str, str]:
    job = jobs.create(title="Backend Engineer")
    snapshot = jobs.add_snapshot(job["id"], raw_text=raw_text, source_kind="page_paste")
    return {
        "snapshot_id": snapshot["id"],
        "raw_text": raw_text,
        "text_sha256": snapshot["text_sha256"],
    }


async def test_structure_keeps_only_quoted_requirements(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    payload = structure_payload(CLEAN_PAGE)
    payload["requirements"] = [  # type: ignore[index]
        *payload["requirements"],  # type: ignore[misc]
        {
            "text": "Owns a Kubernetes platform end to end",
            "category": "tool",
            "importance": "weight",
            "keywords": ["Kubernetes"],
            "jd_quote": "Owns a Kubernetes platform, which the advert never says.",
        },
        {
            "text": "Strong SQL and PostgreSQL skills",
            "category": "skill",
            "importance": "weight",
            "keywords": ["SQL"],
            "jd_quote": "Strong SQL and PostgreSQL skills.",
        },
    ]
    structurer, llm, jobs = build([payload])

    result = await structurer.run(**_prepare(jobs, CLEAN_PAGE))

    assert result.status == "ok"
    assert result.dropped_quotes == 1
    assert result.duplicates == 1
    assert len(result.requirements) == 5
    assert all(item.jd_quote in CLEAN_PAGE for item in result.requirements)
    assert "Kubernetes platform" not in " ".join(item.jd_quote for item in result.requirements)
    assert len(llm.requests) == 1
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(JdRequirement)) == 5


async def test_structure_is_cached_by_extract_key(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    structurer, llm, jobs = build([structure_payload(CLEAN_PAGE)])
    prepared = _prepare(jobs, CLEAN_PAGE)

    first = await structurer.run(**prepared)
    second = await structurer.run(**prepared)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.extraction_id == first.extraction_id
    assert len(second.requirements) == len(first.requirements)
    assert len(llm.requests) == 1
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(JdExtraction)) == 1


async def test_non_job_text_is_refused_and_remembered(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    payload = {"is_job_post": False, "job_count": 0, "requirements": []}
    structurer, llm, jobs = build([payload])
    prepared = _prepare(jobs, NON_JOB_TEXT)

    with pytest.raises(AppError) as first:
        await structurer.run(**prepared)
    assert first.value.code == "JD_NOT_FOUND"
    assert first.value.status_code == 422

    with pytest.raises(AppError) as second:
        await structurer.run(**prepared)
    assert second.value.code == "JD_NOT_FOUND"
    assert len(llm.requests) == 1
    with session_factory() as session:
        assert session.scalar(select(JdExtraction.status)) == "jd_not_found"


async def test_two_jobs_in_one_paste_are_refused(build: Build) -> None:
    payload = {**structure_payload(MULTI_JOB_PAGE), "job_count": 2}
    structurer, _, jobs = build([payload])

    with pytest.raises(AppError) as error:
        await structurer.run(**_prepare(jobs, MULTI_JOB_PAGE))
    assert error.value.code == "JD_MULTIPLE_JOBS"


async def test_provider_failure_is_mapped_to_a_stable_code(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    structurer, _, jobs = build([LLMError("upstream timeout", code="LLM_TIMEOUT")])

    with pytest.raises(AppError) as error:
        await structurer.run(**_prepare(jobs, CLEAN_PAGE))
    assert error.value.code == "LLM_TIMEOUT"
    assert error.value.status_code == 504
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(JdExtraction)) == 0


async def test_too_few_requirements_is_a_warning_not_a_failure(build: Build) -> None:
    payload = structure_payload(CLEAN_PAGE)
    payload["requirements"] = payload["requirements"][:2]  # type: ignore[index]
    structurer, _, jobs = build([payload])

    result = await structurer.run(**_prepare(jobs, CLEAN_PAGE))
    assert result.status == "ok"
    assert result.warnings == ["few_requirements"]
    assert len(result.requirements) == 2


async def test_noisy_page_produces_no_boilerplate(build: Build) -> None:
    structurer, _, jobs = build([structure_payload(NOISY_PAGE)])

    result = await structurer.run(**_prepare(jobs, NOISY_PAGE))
    joined = " ".join(item.text for item in result.requirements).casefold()
    assert "similar jobs" not in joined
    assert "privacy policy" not in joined
    assert len(result.requirements) == 5
