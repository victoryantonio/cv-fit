"""Manual job intake, triage transitions and immutable JD snapshots."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.container import Container
from app.main import create_app
from app.modules.jobs.jd_input import MAX_JD_CHARS
from app.shared.text import sha256_hex
from tests.fixtures.jd_texts import CLEAN_PAGE, INJECTION_PAGE, TRUNCATED_PAGE


@pytest.fixture
def client(container: Container) -> Iterator[TestClient]:
    with TestClient(create_app(container), base_url="http://127.0.0.1") as test_client:
        yield test_client


def _job(client: TestClient) -> str:
    response = client.post("/api/jobs", json={"title": "Backend Engineer", "company": "Acme"})
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_create_and_list_jobs(client: TestClient) -> None:
    job_id = _job(client)
    listing = client.get("/api/jobs", params={"status": "new"}).json()
    assert listing["total"] == 1
    assert listing["items"][0]["id"] == job_id
    assert listing["items"][0]["source"] == "manual"
    assert listing["items"][0]["snapshot_count"] == 0


def test_list_rejects_an_unknown_status(client: TestClient) -> None:
    response = client.get("/api/jobs", params={"status": "zombie"})
    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_status_transitions_follow_the_afd(client: TestClient) -> None:
    job_id = _job(client)
    assert client.patch(f"/api/jobs/{job_id}", json={"status": "shortlisted"}).status_code == 200
    assert client.patch(f"/api/jobs/{job_id}", json={"status": "analyzed"}).status_code == 200
    applied = client.patch(f"/api/jobs/{job_id}", json={"status": "applied"})
    assert applied.status_code == 200
    assert applied.json()["applied_at"] is not None


def test_skipping_a_step_is_rejected(client: TestClient) -> None:
    job_id = _job(client)
    response = client.patch(f"/api/jobs/{job_id}", json={"status": "applied"})
    assert response.status_code == 422
    assert response.json()["details"]["from"] == "new"


def test_dismissed_job_can_return_to_new(client: TestClient) -> None:
    job_id = _job(client)
    client.patch(f"/api/jobs/{job_id}", json={"status": "dismissed"})
    revived = client.patch(f"/api/jobs/{job_id}", json={"status": "new"})
    assert revived.json()["status"] == "new"


def test_outcome_is_recorded(client: TestClient) -> None:
    job_id = _job(client)
    response = client.patch(f"/api/jobs/{job_id}", json={"outcome": "interview"})
    assert response.status_code == 200
    assert response.json()["outcome"] == "interview"


def test_snapshot_is_stored_once_per_distinct_text(client: TestClient) -> None:
    job_id = _job(client)
    first = client.post(f"/api/jobs/{job_id}/snapshots", json={"raw_text": CLEAN_PAGE})
    assert first.status_code == 201
    body = first.json()
    assert body["reused"] is False
    assert body["text_sha256"] == sha256_hex(CLEAN_PAGE)
    assert body["injection_flags"] == []
    assert body["truncation_warning"] is False

    second = client.post(f"/api/jobs/{job_id}/snapshots", json={"raw_text": CLEAN_PAGE})
    assert second.json()["reused"] is True
    assert second.json()["id"] == body["id"]

    third = client.post(f"/api/jobs/{job_id}/snapshots", json={"raw_text": CLEAN_PAGE + "\n\n"})
    assert third.json()["reused"] is False
    assert third.json()["id"] != body["id"]


def test_snapshot_records_injection_flags(client: TestClient) -> None:
    job_id = _job(client)
    body = client.post(f"/api/jobs/{job_id}/snapshots", json={"raw_text": INJECTION_PAGE}).json()
    assert "instruction_override" in body["injection_flags"]


def test_snapshot_records_truncation_as_a_warning(client: TestClient) -> None:
    job_id = _job(client)
    body = client.post(f"/api/jobs/{job_id}/snapshots", json={"raw_text": TRUNCATED_PAGE}).json()
    assert body["truncation_warning"] is True
    assert "mid_sentence" in body["truncation_reasons"]


def test_snapshot_length_limits(client: TestClient) -> None:
    job_id = _job(client)
    too_short = client.post(f"/api/jobs/{job_id}/snapshots", json={"raw_text": "too short"})
    assert too_short.status_code == 422
    assert too_short.json()["details"]["reason"] == "too_short"

    too_long = client.post(
        f"/api/jobs/{job_id}/snapshots", json={"raw_text": "x" * (MAX_JD_CHARS + 1)}
    )
    assert too_long.status_code == 422
    assert too_long.json()["details"]["reason"] == "too_long"


def test_snapshot_of_an_unknown_job_is_not_found(client: TestClient) -> None:
    response = client.post("/api/jobs/missing/snapshots", json={"raw_text": CLEAN_PAGE})
    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_snapshot_detail_returns_the_stored_text(client: TestClient) -> None:
    job_id = _job(client)
    created = client.post(f"/api/jobs/{job_id}/snapshots", json={"raw_text": CLEAN_PAGE}).json()
    detail = client.get(f"/api/jd-snapshots/{created['id']}").json()
    assert detail["raw_text"] == CLEAN_PAGE
    assert detail["job_id"] == job_id
