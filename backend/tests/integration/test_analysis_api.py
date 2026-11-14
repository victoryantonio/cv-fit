"""The HTTP surface over a completed packet: read, rescore, history, 404."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.shared.errors import AppError
from tests.conftest import post_analysis
from tests.integration.analysis_build import Build, make_job, make_version


async def test_history_lists_both_runs_as_comparable(build: Build) -> None:
    container, _ = build(None)
    job_id, snapshot = make_job(container)
    first = await container.analysis.run(
        cv_version_id=make_version(container, "one"), snapshot_id=snapshot["id"]
    )
    second = await container.analysis.run(
        cv_version_id=make_version(container, "two"), snapshot_id=snapshot["id"]
    )

    history = container.analysis.history(job_id)

    assert {item["analysis_id"] for item in history["items"]} == {first["id"], second["id"]}
    assert all(item["comparable"] is True for item in history["items"])
    assert all(item["summary"]["coverage"] == 64 for item in history["items"])
    with pytest.raises(AppError) as raised:
        container.analysis.history("missing-job")
    assert raised.value.code == "NOT_FOUND"


def test_api_runs_reads_patches_and_lists_history(build: Build) -> None:
    container, _ = build(None)
    job_id, snapshot = make_job(container)
    version = make_version(container, "one")

    with TestClient(create_app(container), base_url="http://127.0.0.1") as api:
        body = post_analysis(api, container, cv_version_id=version, snapshot_id=snapshot["id"])

        read = api.get(f"/api/analyses/{body['id']}")
        assert read.status_code == 200, read.text
        assert read.json()["summary"] == body["summary"]

        requirement_id = next(item["id"] for item in body["requirements"] if "AWS" in item["text"])
        patched = api.patch(f"/api/requirements/{requirement_id}", json={"active": False})
        assert patched.status_code == 200, patched.text
        rescored = patched.json()["analyses"][0]["summary"]
        assert rescored["counts"]["gap"] == 0
        assert rescored["coverage"] == 88

        history = api.get(f"/api/jobs/{job_id}/history")
        assert history.status_code == 200, history.text
        items = history.json()["items"]
        assert len(items) == 1
        assert items[0]["comparable"] is True

        missing = api.get("/api/analyses/does-not-exist")
        assert missing.status_code == 404
        assert missing.json()["code"] == "NOT_FOUND"
