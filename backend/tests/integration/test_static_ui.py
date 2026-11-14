"""The static UI mount: assets, deep links, and the `/api` boundary."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from fastapi.testclient import TestClient

from app.container import Container
from app.main import create_app


def _build(dist: Path) -> Path:
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>app</title>", encoding="utf-8")
    (dist / "assets" / "index-abc123.js").write_text("console.log(1)", encoding="utf-8")
    return dist


def _client(container: Container, dist: Path) -> TestClient:
    served = replace(
        container, settings=container.settings.model_copy(update={"ui_dist_dir": dist})
    )
    return TestClient(create_app(served), base_url="http://127.0.0.1")


def test_no_build_serves_the_api_only(container: Container, tmp_path: Path) -> None:
    client = _client(container, tmp_path / "missing")
    assert client.get("/").status_code == 404
    assert client.get("/api/health").status_code == 200


def test_index_and_hashed_assets_are_served(container: Container, tmp_path: Path) -> None:
    client = _client(container, _build(tmp_path / "dist"))
    assert client.get("/").text == "<!doctype html><title>app</title>"
    assert client.get("/assets/index-abc123.js").text == "console.log(1)"


def test_client_route_falls_back_to_the_index(container: Container, tmp_path: Path) -> None:
    client = _client(container, _build(tmp_path / "dist"))
    for path in ("/jobs", "/jobs/abc/history", "/packets/p1"):
        response = client.get(path)
        assert response.status_code == 200, path
        assert "<!doctype html>" in response.text, path


def test_unknown_api_path_stays_json(container: Container, tmp_path: Path) -> None:
    client = _client(container, _build(tmp_path / "dist"))
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["code"] == "NOT_FOUND"


def test_traversal_cannot_escape_the_build(container: Container, tmp_path: Path) -> None:
    dist = _build(tmp_path / "dist")
    secret = tmp_path / "secret.txt"
    secret.write_text("cv text", encoding="utf-8")
    client = _client(container, dist)
    # The catch-all decodes this before routing, so it arrives as a literal path
    # segment sequence rather than a normal lookup.
    response = client.get("/../secret.txt")
    assert response.text != "cv text"
    assert "cv text" not in response.text
