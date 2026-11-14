"""S5 and S6 end to end: what the model proposes, and what the guard lets through.

The model is scripted to propose three kinds of fabrication (a number, a tool and
an empty claim) next to one faithful rewrite. Nothing downstream is faked: the
guard runs against the stored CV text, the rejected rows are persisted with the
rule that blocked them, and the API hides them unless they are asked for.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.container import Container, build_container
from app.main import create_app
from app.modules.analysis.models import Suggestion
from app.modules.cvs.parser import ParsedCv
from app.shared.clock import FixedClock
from app.shared.errors import AppError
from tests.conftest import InMemorySecretStore, post_analysis
from tests.fakes import FakeLLMClient
from tests.fixtures.cover_notes import COVER_OK
from tests.fixtures.jd_texts import CLEAN_PAGE, structure_payload
from tests.integration.analysis_build import make_job, make_version

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPTS_DIR = REPO_ROOT / "prompts"
REQUIREMENT_COUNT = 5
MATCH_RUNS = 1

CV_TEXT = (
    "RINA PRATAMA\n"
    "Backend engineer with six years building payment and ledger services in Python.\n"
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes.\n"
    "Ran the ledger on PostgreSQL and wrote the SQL behind monthly reconciliation.\n"
    "Reviewed merge requests and paired with two junior engineers each week.\n"
)

QUOTE_PYTHON = (
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes."
)
QUOTE_SQL = "Ran the ledger on PostgreSQL and wrote the SQL behind monthly reconciliation."
LINE_MERGE = "Reviewed merge requests and paired with two junior engineers each week."

STRONG_PYTHON: dict[str, Any] = {
    "verdict": "strong",
    "evidence_quote": QUOTE_PYTHON,
    "rationale": "Names the work, the language and the outcome.",
    "missing": [],
}
STRONG_SQL: dict[str, Any] = {
    "verdict": "strong",
    "evidence_quote": QUOTE_SQL,
    "rationale": "Names the database and the query work.",
    "missing": [],
}
GAP_AWS: dict[str, Any] = {
    "verdict": "gap",
    "evidence_quote": None,
    "rationale": "The CV never mentions a cloud provider.",
    "missing": ["AWS", "ECS", "Kubernetes"],
}
PARTIAL_MENTOR: dict[str, Any] = {
    "verdict": "partial",
    "evidence_quote": LINE_MERGE,
    "rationale": "Shows review and pairing, not formal mentoring of mid-level engineers.",
    "missing": ["mid-level engineers"],
}
PARTIAL_ENGLISH: dict[str, Any] = {
    "verdict": "partial",
    "evidence_quote": "Backend engineer with six years building payment and ledger services",
    "rationale": "Shows written work, not a language test.",
    "missing": ["written English"],
}

MATCH_SCRIPT = [STRONG_PYTHON, STRONG_SQL, GAP_AWS, PARTIAL_MENTOR, PARTIAL_ENGLISH]

FAITHFUL: dict[str, Any] = {
    "requirement_index": 0,
    "type": "reword",
    "scope": "job_specific",
    "target_section": "experience",
    "original_text": QUOTE_PYTHON,
    "proposed_text": QUOTE_PYTHON,
    "rationale": "Keeps the runtime cut in the first clause.",
}
INVENTED_METRIC: dict[str, Any] = {
    "requirement_index": 1,
    "type": "reword",
    "scope": "job_specific",
    "target_section": "experience",
    "original_text": QUOTE_PYTHON,
    "proposed_text": f"{QUOTE_PYTHON} Cut infrastructure spend by 87 percent.",
    "rationale": "Adds the cost angle the requirement asks for.",
}
INVENTED_TOOL: dict[str, Any] = {
    "requirement_index": 2,
    "type": "emphasize",
    "scope": "job_specific",
    "target_section": "skills",
    "original_text": QUOTE_SQL,
    "proposed_text": "Ran the ledger on PostgreSQL and Kubernetes.",
    "rationale": "Mentions the orchestration platform.",
}
EMPTY_CLAIM: dict[str, Any] = {
    "requirement_index": 0,
    "type": "emphasize",
    "scope": "general",
    "target_section": "summary",
    "original_text": None,
    "proposed_text": "A results-driven backend engineer.",
    "rationale": "Opens with impact.",
}

BATCH: dict[str, Any] = {
    "suggestions": [FAITHFUL, INVENTED_METRIC, INVENTED_TOOL, EMPTY_CLAIM],
}

NO_SUGGESTIONS: dict[str, Any] = {"suggestions": []}


class NamedParser:
    """One CV, registered under the name the upload uses."""

    def __init__(self, text: str) -> None:
        self._text = text

    def parse(self, data: bytes, *, file_name: str) -> ParsedCv:
        return ParsedCv(text=self._text, sections={"other": self._text}, warnings=[], kind="docx")


def _script(suggest: dict[str, Any]) -> list[object]:
    """Extraction, then three identical match runs per requirement, then S5, then S7."""
    run: list[object] = [payload for payload in MATCH_SCRIPT for _ in range(MATCH_RUNS)]
    run.append(suggest)
    run.append(COVER_OK)
    return [structure_payload(CLEAN_PAGE), *run]


Build = Callable[[list[object] | None], tuple[Container, FakeLLMClient]]


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
        llm = FakeLLMClient(script or _script(BATCH))
        container = build_container(
            configured,
            engine=schema,
            secret_store=secret_store,
            clock=clock,
            llm_client=llm,
            document_parser=NamedParser(CV_TEXT),
        )
        return container, llm

    return factory


async def test_visible_suggestions_are_the_ones_that_survived_the_guard(build: Build) -> None:
    container, llm = build(None)
    _, snapshot = make_job(container)

    payload = await container.analysis.run(
        cv_version_id=make_version(container, "one"), snapshot_id=snapshot["id"]
    )

    assert len(llm.requests) == 1 + REQUIREMENT_COUNT * MATCH_RUNS + 2
    assert [item["proposed_text"] for item in payload["suggestions"]] == [QUOTE_PYTHON]
    assert payload["suggestion_provenance"] == {
        "total": 4,
        "visible": 1,
        "hidden": 3,
        "rejected_by_rule": {
            "banned_phrase": 1,
            "numbers_not_in_cv": 1,
            "unknown_vocabulary": 1,
        },
    }
    assert "suggestions_rejected" not in payload


async def test_rejected_suggestions_are_stored_with_the_rule_that_blocked_them(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    container, _ = build(None)
    _, snapshot = make_job(container)

    payload = await container.analysis.run(
        cv_version_id=make_version(container, "one"), snapshot_id=snapshot["id"]
    )
    hidden = container.analysis.get(payload["id"], include_rejected=True)["suggestions_rejected"]
    by_status = {item["guard_status"]: item for item in hidden}

    assert set(by_status) == {
        "rejected_banned_phrase",
        "rejected_numbers_not_in_cv",
        "rejected_unknown_vocabulary",
    }
    assert "87" in by_status["rejected_numbers_not_in_cv"]["guard_reason"]
    assert "kubernetes" in by_status["rejected_unknown_vocabulary"]["guard_reason"]
    assert "results-driven" in by_status["rejected_banned_phrase"]["guard_reason"]
    with session_factory() as session:
        stored = session.scalar(select(func.count()).select_from(Suggestion))
    assert stored == 4


async def test_a_gap_the_model_will_not_touch_is_reported_in_code(build: Build) -> None:
    """No rewrite for an uncovered gap means no suggestion; the note comes from code."""
    container, _ = build(_script(NO_SUGGESTIONS))
    _, snapshot = make_job(container)

    payload = await container.analysis.run(
        cv_version_id=make_version(container, "one"), snapshot_id=snapshot["id"]
    )

    # One gap, two partials: only the gap earns a note, because a partial has evidence.
    notes = payload["suggestions"]
    assert [item["type"] for item in notes] == ["gap_note"]
    assert notes[0]["proposed_text"] is None
    assert notes[0]["guard_status"] == "pass"
    assert notes[0]["rationale"].startswith("No CV evidence for: ")


def test_api_hides_rejected_suggestions_and_refuses_to_accept_them(build: Build) -> None:
    container, _ = build(None)
    _, snapshot = make_job(container)

    with TestClient(create_app(container), base_url="http://127.0.0.1") as api:
        body = post_analysis(
            api, container, cv_version_id=make_version(container, "one"), snapshot_id=snapshot["id"]
        )
        assert len(body["suggestions"]) == 1

        visible = body["suggestions"][0]
        accepted = api.patch(
            f"/api/suggestions/{visible['id']}", json={"decision": "accepted", "reason": "ok"}
        )
        assert accepted.status_code == 200, accepted.text
        assert accepted.json()["suggestion"]["decision"] == "accepted"
        assert accepted.json()["suggestion_provenance"]["hidden"] == 3

        full = api.get(f"/api/analyses/{body['id']}", params={"include_rejected": True})
        assert full.status_code == 200, full.text
        blocked = full.json()["suggestions_rejected"][0]
        refused = api.patch(
            f"/api/suggestions/{blocked['id']}", json={"decision": "accepted", "reason": None}
        )
        assert refused.status_code == 409
        assert refused.json()["code"] == "GUARD_BLOCKED"

        dismissed = api.patch(
            f"/api/suggestions/{blocked['id']}", json={"decision": "rejected", "reason": "invented"}
        )
        assert dismissed.status_code == 200, dismissed.text
        assert dismissed.json()["suggestion"]["decision_reason"] == "invented"

        unknown = api.patch("/api/suggestions/nope", json={"decision": "accepted"})
        assert unknown.status_code == 404
        assert unknown.json()["code"] == "NOT_FOUND"

        bad = api.patch(f"/api/suggestions/{visible['id']}", json={"decision": "maybe"})
        assert bad.status_code == 422
        assert bad.json()["code"] == "INVALID_DECISION"


async def test_a_decision_the_tool_does_not_record_is_refused(build: Build) -> None:
    container, _ = build(None)
    _, snapshot = make_job(container)
    payload = await container.analysis.run(
        cv_version_id=make_version(container, "one"), snapshot_id=snapshot["id"]
    )
    visible = payload["suggestions"][0]

    with pytest.raises(AppError) as raised:
        container.analysis.set_suggestion_decision(visible["id"], decision="maybe")
    assert raised.value.code == "INVALID_DECISION"

