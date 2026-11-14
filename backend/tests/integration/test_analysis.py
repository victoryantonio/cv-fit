"""S2..S4 end to end: grounded verdicts, voting, cache reuse and read-time scoring.

The LLM is scripted, but nothing downstream of it is faked: quotes are checked
against the stored CV text, votes are tallied, and every number in the read
payload is recomputed from the stored rows.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.modules.analysis import queries
from app.modules.analysis.export import render_markdown
from app.modules.analysis.models import Analysis, JdExtraction, RequirementMatch
from tests.fixtures.cover_notes import COVER_TEXT
from tests.fixtures.jd_texts import CLEAN_PAGE, structure_payload
from tests.integration.analysis_build import (
    MATCH_RUNS,
    QUOTE_PYTHON,
    QUOTE_SQL,
    REQUIREMENT_COUNT,
    UNGROUNDED,
    Build,
    make_job,
    make_version,
    per_run_script,
)


def _check_votes(payload: dict[str, Any], calls: int) -> None:
    assert payload["cache_hit"] is False
    assert payload["status"] == "ok"
    assert payload["match_runs"] == MATCH_RUNS
    assert calls == 1 + REQUIREMENT_COUNT * MATCH_RUNS + 2
    assert [item["verdict"] for item in payload["matches"]] == [
        "strong",
        "strong",
        "gap",
        "partial",
        "partial",
    ]
    for match in payload["matches"]:
        assert match["votes"] == {match["verdict"]: MATCH_RUNS}
        assert match["agreement"] == 1.0
    assert payload["matches"][2]["evidence_quote"] is None
    assert payload["matches"][0]["evidence_quote"] == QUOTE_PYTHON


def _check_summary(summary: dict[str, Any]) -> None:
    assert summary["coverage"] == 64
    assert summary["label"] == "reasonable_fit"
    assert summary["counts"] == {"strong": 2, "partial": 2, "gap": 1}
    assert summary["must_have"] == {"met": 2, "total": 3, "coverage": 0.67}
    assert summary["knockout_gaps"] == []
    assert [item["evidence_quote"] for item in summary["strongest"]] == [
        QUOTE_PYTHON,
        QUOTE_SQL,
    ]
    # Only must-have gaps are reported, and the two nice-to-have partials are not.
    assert [item["verdict"] for item in summary["biggest_gaps"]] == ["gap"]


def _check_cover(cover: dict[str, Any]) -> None:
    assert cover["is_draft"] is True
    assert cover["guard_status"] == "pass"
    assert cover["text"] == COVER_TEXT
    assert cover["word_count"] == len(COVER_TEXT.split())


def _check_stored_calls(session_factory: sessionmaker[Session], payload: dict[str, Any]) -> None:
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(RequirementMatch)) == (
            REQUIREMENT_COUNT
        )
        # The calls this run made belong to the packet it produced, which is the
        # only reason tokens and latency can be measured per analysis at all.
        calls = queries.calls_for_analysis(session, payload["id"])
        assert len(calls) == 1 + REQUIREMENT_COUNT * MATCH_RUNS + 2
        assert {call.analysis_id for call in calls} == {payload["id"]}


async def test_pipeline_stores_grounded_verdicts_and_votes(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    container, llm = build(None)
    _, snapshot = make_job(container)
    version = make_version(container, "one")

    payload = await container.analysis.run(cv_version_id=version, snapshot_id=snapshot["id"])

    _check_votes(payload, len(llm.requests))
    _check_summary(payload["summary"])
    _check_cover(payload["cover_note"])
    _check_stored_calls(session_factory, payload)


async def test_second_run_reuses_the_stored_analysis(build: Build) -> None:
    container, llm = build(None)
    _, snapshot = make_job(container)
    version = make_version(container, "one")

    first = await container.analysis.run(cv_version_id=version, snapshot_id=snapshot["id"])
    calls = len(llm.requests)
    second = await container.analysis.run(cv_version_id=version, snapshot_id=snapshot["id"])

    assert second["cache_hit"] is True
    assert second["id"] == first["id"]
    assert len(llm.requests) == calls


async def test_two_cv_versions_share_one_extraction(
    build: Build, session_factory: sessionmaker[Session]
) -> None:
    container, llm = build(None)
    _, snapshot = make_job(container)
    first_version = make_version(container, "one")
    second_version = make_version(container, "two")

    first = await container.analysis.run(cv_version_id=first_version, snapshot_id=snapshot["id"])
    second = await container.analysis.run(cv_version_id=second_version, snapshot_id=snapshot["id"])

    assert first["extraction_id"] == second["extraction_id"]
    assert first["id"] != second["id"]
    # The JD is structured once; the second run only matches, suggests and writes.
    assert len(llm.requests) == 1 + 2 * (REQUIREMENT_COUNT * MATCH_RUNS + 2)
    with session_factory() as session:
        assert session.scalar(select(func.count()).select_from(JdExtraction)) == 1
        assert session.scalar(select(func.count()).select_from(Analysis)) == 2


async def test_deactivated_requirement_rescores_without_a_model_call(build: Build) -> None:
    container, llm = build(None)
    _, snapshot = make_job(container)
    version = make_version(container, "one")
    payload = await container.analysis.run(cv_version_id=version, snapshot_id=snapshot["id"])
    calls = len(llm.requests)
    aws = next(item for item in payload["requirements"] if "AWS" in item["text"])

    patched = container.analysis.set_requirement_active(aws["id"], active=False)

    assert patched["requirement"]["active"] is False
    rescored = patched["analyses"][0]["summary"]
    assert rescored["counts"] == {"strong": 2, "partial": 2, "gap": 0}
    assert rescored["coverage"] == 88
    assert rescored["label"] == "strong_fit"
    assert rescored["must_have"] == {"met": 2, "total": 2, "coverage": 1.0}
    assert len(llm.requests) == calls


async def test_ungrounded_quote_never_wins_a_vote(build: Build) -> None:
    container, llm = build([structure_payload(CLEAN_PAGE)])
    llm.repeat(UNGROUNDED)
    _, snapshot = make_job(container)
    version = make_version(container, "one")

    payload = await container.analysis.run(cv_version_id=version, snapshot_id=snapshot["id"])

    assert [item["verdict"] for item in payload["matches"]] == ["gap"] * REQUIREMENT_COUNT
    assert all("ungrounded_evidence" in item["flags"] for item in payload["matches"])
    assert all(item["evidence_quote"] is None for item in payload["matches"])
    assert payload["summary"]["coverage"] == 0
    assert payload["summary"]["label"] == "stretch"
    assert payload["summary"]["strongest"] == []


async def test_job_details_fall_back_to_the_job_row_never_invented(build: Build) -> None:
    """A post that never names the role still gets the job's own title.

    The row exists because the user pasted the text into it, so borrowing that
    title is not fabrication; a field missing in both places stays empty.
    """
    anonymous = {**structure_payload(CLEAN_PAGE), "title": None}
    container, _ = build([anonymous, *per_run_script()])
    job_id, snapshot = make_job(container)

    payload = await container.analysis.run(
        cv_version_id=make_version(container, "one"), snapshot_id=snapshot["id"]
    )

    assert payload["job_id"] == job_id
    assert payload["job"]["title"] == "Senior Backend Engineer"
    # The structure named the company, so that is what the packet reports.
    assert payload["job"]["company"] == "Acme Payments"
    assert render_markdown(payload).startswith(
        "# Application packet: Senior Backend Engineer at Acme Payments\n"
    )
