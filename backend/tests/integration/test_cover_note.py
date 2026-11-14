"""S7 and S8 through the service: store, edit, regenerate, export.

The note is a draft at every step, an edit never erases what the model wrote, a
rejected regeneration never destroys the packet, and the export never tells the
user whether to send the application.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.container import Container, build_container
from app.main import create_app
from app.modules.analysis.enums import Step
from app.modules.analysis.models import Analysis
from app.modules.cvs.parser import ParsedCv
from app.shared.clock import FixedClock
from app.shared.errors import AppError
from tests.conftest import InMemorySecretStore, post_analysis
from tests.fakes import FakeLLMClient
from tests.fixtures.cover_notes import COVER_OK, COVER_TEXT
from tests.fixtures.documents import build_docx
from tests.fixtures.jd_texts import CLEAN_PAGE, structure_payload
from tests.fixtures.matches import ALL_GAP, CV_TEXT, MATCH_SCRIPT

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "prompts"
MATCH_RUNS = 1
REQUIREMENT_COUNT = 5

INVENTED: dict[str, Any] = {
    "text": f"{COVER_TEXT} Settlement now finishes 94 percent faster.",
    "asserted_requirement_indexes": [0, 1],
}


class NamedParser:
    """One CV, registered under the name the upload uses."""

    def parse(self, data: bytes, *, file_name: str) -> ParsedCv:
        return ParsedCv(text=CV_TEXT, sections={"other": CV_TEXT}, warnings=[], kind="docx")


def _script(*covers: dict[str, Any], matches: list[dict[str, Any]] | None = None) -> list[object]:
    """Extraction, then three identical judgment runs per requirement, then S5, then S7."""
    run: list[object] = [
        payload for payload in (matches or MATCH_SCRIPT) for _ in range(MATCH_RUNS)
    ]
    run.append({"suggestions": []})
    run.extend(covers)
    return [structure_payload(CLEAN_PAGE), *run]


Build = Callable[[list[object]], tuple[Container, FakeLLMClient]]


@pytest.fixture
def build(
    settings: Settings,
    schema: Engine,
    secret_store: InMemorySecretStore,
    clock: FixedClock,
) -> Build:
    configured = settings.model_copy(update={"prompts_dir": PROMPTS_DIR})
    parser = NamedParser()

    def factory(script: list[object]) -> tuple[Container, FakeLLMClient]:
        llm = FakeLLMClient(script)
        container = build_container(
            configured,
            engine=schema,
            secret_store=secret_store,
            clock=clock,
            llm_client=llm,
            document_parser=parser,
        )
        return container, llm

    return factory


def _inputs(container: Container) -> dict[str, str]:
    job = container.jobs.create(title="Senior Backend Engineer")
    snapshot = container.jobs.add_snapshot(job["id"], raw_text=CLEAN_PAGE, source_kind="page_paste")
    cv = container.cvs.create(label="CV one")
    version = container.cvs.add_version(cv["id"], file_name="one.docx", data=build_docx())
    return {"cv_version_id": str(version["id"]), "snapshot_id": str(snapshot["id"])}


def _stored(session_factory: sessionmaker[Session]) -> Analysis:
    with session_factory() as session:
        return session.scalars(select(Analysis)).one()


def _api(container: Container) -> TestClient:
    return TestClient(create_app(container), base_url="http://127.0.0.1")


async def test_the_note_is_stored_with_the_verdict_that_let_it_through(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    container, _ = build(_script(COVER_OK))

    payload = await container.analysis.run(**_inputs(container))

    cover = payload["cover_note"]
    assert cover["text"] == COVER_TEXT
    assert cover["generated"] == COVER_TEXT
    assert cover["edited"] is None
    assert cover["guard_status"] == "pass"
    assert cover["guard_reason"] is None
    assert cover["is_draft"] is True
    assert cover["word_count"] == len(COVER_TEXT.split())

    stored = _stored(session_factory)
    assert stored.cover_note == COVER_TEXT
    assert stored.cover_note_guard == "pass"
    assert stored.cover_note_reason is None
    assert stored.cover_note_edited is None


def test_an_edit_keeps_what_the_model_wrote(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    container, _ = build(_script(COVER_OK))
    with _api(container) as api:
        body = post_analysis(api, container, **_inputs(container))
        edited_text = f"{COVER_TEXT} I can start in March."
        response = api.patch(f"/api/analyses/{body['id']}/cover-note", json={"text": edited_text})
        assert response.status_code == 200, response.text
        cover = response.json()["cover_note"]
        assert cover["text"] == edited_text
        assert cover["generated"] == COVER_TEXT
        assert cover["edited"] == edited_text
        assert cover["is_draft"] is True
        assert cover["word_count"] == len(edited_text.split())

        blank = api.patch(f"/api/analyses/{body['id']}/cover-note", json={"text": ""})
        assert blank.status_code == 422

    stored = _stored(session_factory)
    assert stored.cover_note == COVER_TEXT
    assert stored.cover_note_edited == f"{COVER_TEXT} I can start in March."


async def test_regenerating_replaces_the_edit(build: Build) -> None:
    container, _ = build(_script(COVER_OK, COVER_OK))
    payload = await container.analysis.run(**_inputs(container))
    container.analysis.set_cover_note_edited(payload["id"], text=f"{COVER_TEXT} Edited.")

    again = await container.analysis.regenerate_cover_note(payload["id"])

    assert again["cover_note"]["text"] == COVER_TEXT
    assert again["cover_note"]["edited"] is None
    assert again["cover_note"]["guard_status"] == "pass"


async def test_a_rejected_regeneration_leaves_the_packet_alone(build: Build) -> None:
    container, _ = build(_script(COVER_OK, INVENTED, INVENTED))
    payload = await container.analysis.run(**_inputs(container))

    with pytest.raises(AppError) as raised:
        await container.analysis.regenerate_cover_note(payload["id"])

    assert raised.value.code == "COVER_NOTE_REJECTED"
    assert raised.value.details["guard_status"] == "rejected_numbers_not_in_cv"
    assert "94" in raised.value.details["guard_reason"]
    kept = container.analysis.get(payload["id"])["cover_note"]
    assert kept["text"] == COVER_TEXT
    assert kept["guard_status"] == "pass"


async def test_nothing_to_assert_means_no_note_and_no_call(build: Build, session_factory) -> None:
    container, llm = build(_script(matches=ALL_GAP))

    payload = await container.analysis.run(**_inputs(container))

    cover = payload["cover_note"]
    assert cover["text"] is None
    assert cover["guard_status"] == "no_strong_matches"
    assert cover["guard_reason"] is not None
    assert len(llm.requests) == 1 + REQUIREMENT_COUNT * MATCH_RUNS + 1
    assert all(request.step != Step.S7_COVER_NOTE for request in llm.requests)
    assert _stored(session_factory).cover_note is None


def test_the_export_describes_and_never_advises(build: Build) -> None:
    container, _ = build(_script(COVER_OK))

    with _api(container) as api:
        body = post_analysis(api, container, **_inputs(container))
        response = api.get(f"/api/analyses/{body['id']}/export.md")

    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/markdown")
    text = response.text
    order = [
        "# Application packet",
        "## Fit summary",
        "## Must-have requirements",
        "## Matches (verified)",
        "## Partial",
        "## CV suggestions",
        "## Cover note (draft)",
    ]
    positions = [text.index(heading) for heading in order]
    assert positions == sorted(positions)
    assert COVER_TEXT in text
    assert "Every claim in it was checked against a quote" in text
    for word in ("apply", "skip", "chance", "recommend"):
        assert re.search(rf"\b{word}\b", text, re.IGNORECASE) is None, word
