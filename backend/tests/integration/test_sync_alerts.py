"""Alert sync: idempotency, URL dedupe, pre-filter reasons, honest failures (FR-06, FR-07)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.container import Container
from app.main import create_app
from app.modules.jobs.ports import (
    AlertCard,
    AlertDetail,
    AlertMessage,
    AlertSourceError,
    JobAlertSource,
)
from app.modules.jobs.prefilter import PrefilterCriteria
from app.modules.jobs.service import JobService
from app.shared.clock import FixedClock

RECEIVED = datetime(2025, 1, 2, 8, 30, tzinfo=UTC)


class FakeAlertSource:
    """Honors `JobAlertSource`: same names, same error type, keyword-only list."""

    def __init__(self, messages: Sequence[AlertMessage], details: dict[str, Any]) -> None:
        self.messages = list(messages)
        self.details = details
        self.list_calls: list[tuple[datetime | None, int]] = []

    async def list_alerts(
        self, *, since: datetime | None = None, limit: int = 25
    ) -> list[AlertMessage]:
        self.list_calls.append((since, limit))
        return self.messages[:limit]

    async def fetch_alert(self, message_id: str) -> AlertDetail:
        value = self.details[message_id]
        if isinstance(value, Exception):
            raise value
        assert isinstance(value, AlertDetail)
        return value


def _message(message_id: str) -> AlertMessage:
    return AlertMessage(message_id=message_id, received_at=RECEIVED)


def _detail(message_id: str, *cards: AlertCard) -> AlertDetail:
    return AlertDetail(message_id=message_id, received_at=RECEIVED, cards=list(cards))


def _card(title: str, *, company: str | None = None, location: str | None = None, url=None):
    return AlertCard(title=title, company=company, location=location, url=url)


def _app(container: Container, source: JobAlertSource | None, **criteria: Any) -> TestClient:
    """Swap only the jobs service: the rest of the container stays as built."""
    jobs = JobService(
        session_factory=container.session_factory,
        clock=container.clock,
        alert_source=source,
        criteria=lambda: PrefilterCriteria(**criteria),
    )
    return TestClient(create_app(replace(container, jobs=jobs)), base_url="http://127.0.0.1")


@pytest.fixture
def source() -> FakeAlertSource:
    return FakeAlertSource(
        messages=[_message("m1")],
        details={
            "m1": _detail(
                "m1",
                _card(
                    "Senior AI Engineer",
                    company="Westpac",
                    location="Sydney, NSW",
                    url="https://au.linkedin.com/jobs/view/101?trk=alert",
                ),
                _card("Analyst", company="Acme", location="Melbourne, VIC"),
            )
        },
    )


def _sync(client: TestClient, **payload: Any) -> dict[str, Any]:
    response = client.post("/api/jobs/sync-alerts", json=payload or {})
    assert response.status_code == 200, response.text
    return response.json()


def test_a_sync_stores_every_card(container: Container, source: FakeAlertSource) -> None:
    with _app(container, source) as client:
        report = _sync(client)
        assert report["messages"] == 1
        assert report["new"] == 2
        assert report["duplicate"] == 0
        assert report["filtered"] == 0
        assert report["parse_failed"] == []
        assert report["synced_at"] is not None

        listing = client.get("/api/jobs").json()
        assert listing["total"] == 2
        job = next(item for item in listing["items"] if item["title"] == "Senior AI Engineer")
        assert job["source"] == "gmail_alert"
        assert job["company"] == "Westpac"
        assert job["received_at"] is not None
        assert job["status"] == "new"


def test_a_second_sync_adds_nothing(container: Container, source: FakeAlertSource) -> None:
    with _app(container, source) as client:
        assert _sync(client)["new"] == 2
        second = _sync(client)
        assert second["new"] == 0
        assert second["duplicate"] == 2
        assert client.get("/api/jobs").json()["total"] == 2


def test_the_same_posting_with_other_tracking_dedupes(
    container: Container, source: FakeAlertSource
) -> None:
    source.details["m1"] = _detail(
        "m1",
        _card("Data Engineer", url="https://au.linkedin.com/jobs/view/77?trk=one"),
        _card("Data Engineer", url="https://au.linkedin.com/jobs/view/77?trk=two&midToken=x"),
    )
    with _app(container, source) as client:
        report = _sync(client)
        assert report["new"] == 1
        assert report["duplicate"] == 1
        assert client.get("/api/jobs").json()["items"][0]["url"] == (
            "https://au.linkedin.com/jobs/view/77"
        )


def test_the_prefilter_records_a_reason_without_deleting_the_job(
    container: Container, source: FakeAlertSource
) -> None:
    source.details["m1"] = _detail(
        "m1",
        _card("Principal Product Manager", company="Bigco", location="Sydney, NSW"),
        _card("Senior AI Engineer", company="Westpac", location="Sydney, NSW"),
    )
    with _app(container, source, exclude_keywords=("principal",)) as client:
        report = _sync(client)
        assert report["new"] == 2
        assert report["filtered"] == 1

        set_aside = client.get("/api/jobs", params={"filtered": "true"}).json()
        kept = client.get("/api/jobs", params={"filtered": "false"}).json()
        assert [item["title"] for item in set_aside["items"]] == ["Principal Product Manager"]
        assert [item["title"] for item in kept["items"]] == ["Senior AI Engineer"]
        assert set_aside["items"][0]["filter_reason"] == 'excluded keyword: "principal"'

        revived = client.patch(f"/api/jobs/{set_aside['items'][0]['id']}", json={"keep": True})
        assert revived.status_code == 200
        assert revived.json()["filter_reason"] is None


def test_an_email_with_no_cards_is_reported_not_dropped(container: Container) -> None:
    source = FakeAlertSource(
        messages=[_message("m1"), _message("m2")],
        details={"m1": _detail("m1"), "m2": _detail("m2", _card("Analyst"))},
    )
    with _app(container, source) as client:
        report = _sync(client)
        assert report["new"] == 1
        assert report["parse_failed"] == ["m1"]


def test_one_unparsable_email_does_not_stop_the_rest(container: Container) -> None:
    source = FakeAlertSource(
        messages=[_message("m1"), _message("m2")],
        details={
            "m1": AlertSourceError("that email is not readable", code="ALERT_PARSE_FAILED"),
            "m2": _detail("m2", _card("Analyst")),
        },
    )
    with _app(container, source) as client:
        report = _sync(client)
        assert report["parse_failed"] == ["m1"]
        assert report["new"] == 1


def test_an_expired_token_stops_the_sync(container: Container) -> None:
    source = FakeAlertSource(
        messages=[_message("m1")],
        details={"m1": AlertSourceError("reconnect please", code="GMAIL_AUTH_EXPIRED")},
    )
    with _app(container, source) as client:
        response = client.post("/api/jobs/sync-alerts", json={})
        assert response.status_code == 401
        assert response.json()["code"] == "GMAIL_AUTH_EXPIRED"
        assert client.get("/api/jobs").json()["total"] == 0


def test_without_a_helper_the_sync_says_so(container: Container) -> None:
    with _app(container, None) as client:
        response = client.post("/api/jobs/sync-alerts", json={})
        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "GMAIL_NOT_CONNECTED"
        assert "app.mcp_gmail auth" in body["details"]["hint"]


def test_the_limit_reaches_the_source(container: Container, source: FakeAlertSource) -> None:
    source.messages = [_message(f"m{index}") for index in range(5)]
    source.details.update({f"m{index}": _detail(f"m{index}") for index in range(5)})
    with _app(container, source) as client:
        report = _sync(client, limit=2)
        assert report["messages"] == 2
        assert source.list_calls == [(None, 2)]


@pytest.mark.parametrize("limit", [0, 51])
def test_a_limit_outside_the_range_is_rejected(
    container: Container, source: FakeAlertSource, limit: int
) -> None:
    with _app(container, source) as client:
        response = client.post("/api/jobs/sync-alerts", json={"limit": limit})
        assert response.status_code == 422
        assert response.json()["code"] == "VALIDATION_ERROR"
        assert source.list_calls == []


def test_a_long_remote_title_is_truncated_not_rejected(container: Container) -> None:
    source = FakeAlertSource(
        messages=[_message("m1")],
        details={"m1": _detail("m1", _card(f"  Engineer\n{'x' * 400}  "))},
    )
    with _app(container, source) as client:
        assert _sync(client)["new"] == 1
        title = client.get("/api/jobs").json()["items"][0]["title"]
        assert len(title) == 200
        assert "\n" not in title


def test_a_card_with_no_title_is_a_parse_failure(container: Container) -> None:
    source = FakeAlertSource(
        messages=[_message("m1")],
        details={"m1": _detail("m1", _card("   "))},
    )
    with _app(container, source) as client:
        report = _sync(client)
        assert report["new"] == 0
        assert report["parse_failed"] == ["m1"]


def test_a_sync_records_when_it_ran(container: Container, source: FakeAlertSource) -> None:
    with _app(container, source) as client:
        assert client.get("/api/jobs/sync-status").json() == {
            "source": "gmail",
            "synced_at": None,
        }

        _sync(client)
        status = client.get("/api/jobs/sync-status").json()
        assert status["source"] == "gmail"
        assert status["synced_at"].startswith("2025-01-02T09:00")


def test_a_sync_with_nothing_new_still_moves_the_timestamp(
    container: Container, source: FakeAlertSource, clock: FixedClock
) -> None:
    with _app(container, source) as client:
        _sync(client)
        clock.advance(3600)
        assert _sync(client)["new"] == 0
        status = client.get("/api/jobs/sync-status").json()
        assert status["synced_at"].startswith("2025-01-02T10:00")
