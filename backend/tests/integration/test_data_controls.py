"""Data controls: the counts must name exactly what a purge removes (FR-26)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.container import Container
from app.modules.platform.health import GMAIL_TOKEN_NAME
from tests.fixtures.jd_texts import CLEAN_PAGE


def _seed(client: TestClient) -> None:
    cv = client.post("/api/cvs", json={"label": "Backend"}).json()
    assert cv["id"]
    job = client.post("/api/jobs", json={"title": "Backend Engineer"}).json()
    snapshot = client.post(
        f"/api/jobs/{job['id']}/snapshots", json={"raw_text": CLEAN_PAGE}
    )
    assert snapshot.status_code == 201


def test_summary_counts_match_what_the_purge_deletes(
    client: TestClient, container: Container
) -> None:
    _seed(client)
    before = client.get("/api/data").json()

    assert before["counts"]["job_posting"] == 1
    assert before["counts"]["jd_snapshot"] == 1
    assert before["counts"]["cv"] == 1
    assert before["total_rows"] == sum(before["counts"].values())
    assert before["database"]["bytes"] > 0

    purged = client.post("/api/data/purge", json={"confirm": "DELETE"})
    assert purged.status_code == 200
    deleted = purged.json()["deleted"]
    assert deleted["job_posting"] == 1
    assert deleted["jd_snapshot"] == 1
    # Settings are configuration, not the user's data: they are not in the list.
    assert "app_setting" not in deleted

    after = client.get("/api/data").json()
    assert after["counts"]["job_posting"] == 0
    assert after["counts"]["jd_snapshot"] == 0
    assert after["counts"]["cv"] == 0


def test_settings_survive_a_purge(client: TestClient) -> None:
    """Losing the model config inside "delete my data" would be a surprise."""
    client.put("/api/settings", json={"criteria": {"include_keywords": ["python"]}})

    client.post("/api/data/purge", json={"confirm": "DELETE"})

    settings = client.get("/api/settings").json()
    assert settings["criteria"]["include_keywords"] == ["python"]


def test_purge_needs_the_word_delete(client: TestClient) -> None:
    _seed(client)

    refused = client.post("/api/data/purge", json={"confirm": "yes"})

    assert refused.status_code == 400
    body = refused.json()
    assert body["code"] == "PURGE_CONFIRM_REQUIRED"
    assert body["details"]["expected"] == "DELETE"
    assert client.get("/api/data").json()["counts"]["job_posting"] == 1


def test_purge_removes_stored_uploads(client: TestClient, settings: Settings) -> None:
    directory = settings.data_dir / "uploads"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "abc.pdf").write_bytes(b"%PDF-1.4")
    assert client.get("/api/data").json()["uploads"]["files"] == 1

    purged = client.post("/api/data/purge", json={"confirm": "DELETE"}).json()

    assert purged["uploads_deleted"] == 1
    assert list(directory.iterdir()) == []


def test_export_returns_the_rows_the_user_owns(client: TestClient) -> None:
    _seed(client)

    export = client.get("/api/data/export").json()

    assert export["exported_at"]
    assert export["tables"]["job_posting"][0]["title"] == "Backend Engineer"
    assert export["tables"]["jd_snapshot"][0]["raw_text"] == CLEAN_PAGE


def test_backup_writes_a_readable_copy(client: TestClient, settings: Settings) -> None:
    _seed(client)

    result = client.post("/api/backup")

    assert result.status_code == 200
    body = result.json()
    path = Path(body["path"])
    assert path.exists()
    assert path.parent == settings.data_dir / "backups"
    assert body["bytes"] == path.stat().st_size
    with sqlite3.connect(path) as copy:
        assert copy.execute("SELECT COUNT(*) FROM cv").fetchone()[0] == 1


def test_two_backups_in_the_same_second_do_not_overwrite(
    client: TestClient, container: Container
) -> None:
    """The test clock is frozen, so a naive filename would collide."""
    first = client.post("/api/backup").json()["path"]
    second = client.post("/api/backup").json()["path"]

    assert first != second
    assert Path(second).exists()


def test_gmail_disconnect_forgets_only_the_token(
    client: TestClient, container: Container
) -> None:
    container.secret_store.set(GMAIL_TOKEN_NAME, "token")
    assert client.get("/api/health").json()["gmail"] == "connected"

    assert client.post("/api/gmail/disconnect").json() == {"status": "not_connected"}

    assert container.secret_store.get(GMAIL_TOKEN_NAME) is None
    assert client.get("/api/health").json()["gmail"] == "not_connected"


def test_gmail_disconnect_is_quiet_when_nothing_is_connected(client: TestClient) -> None:
    response = client.post("/api/gmail/disconnect")

    assert response.status_code == 200
    assert response.json() == {"status": "not_connected"}
