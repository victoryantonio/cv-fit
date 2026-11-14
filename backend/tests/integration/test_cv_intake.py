"""CV intake end to end: validation, redaction, storage and the Parser View."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from app.config import Settings
from app.container import Container, build_container
from app.main import create_app
from app.modules.cvs import queries
from app.modules.cvs.parser import ParsedCv
from app.shared.clock import FixedClock
from tests.conftest import InMemorySecretStore
from tests.fakes import FakeDocumentParser
from tests.fixtures.documents import build_docx

CV_BODY = (
    "RINA PRATAMA\n"
    "rina.pratama@example.com | +62 812-3456-7890\n"
    "Jl. Melati No. 12, Bandung 40123\n"
    "SUMMARY\n"
    "Backend engineer with six years building payment and ledger services in Python.\n"
    "EXPERIENCE\n"
    "Rebuilt the settlement worker in Python and cut end-of-day runtime from 40 to 6 minutes.\n"
)

PARSED = ParsedCv(
    text=CV_BODY,
    sections={"other": CV_BODY.split("SUMMARY")[0].strip(), "summary": "SUMMARY"},
    warnings=["no_sections_detected"],
    kind="docx",
)


@pytest.fixture
def subject_container(
    settings: Settings,
    schema: Engine,
    secret_store: InMemorySecretStore,
    clock: FixedClock,
) -> Container:
    return build_container(
        settings,
        engine=schema,
        secret_store=secret_store,
        clock=clock,
        document_parser=FakeDocumentParser(parsed=PARSED),
    )


@pytest.fixture
def api(subject_container: Container) -> Iterator[TestClient]:
    with TestClient(create_app(subject_container), base_url="http://127.0.0.1") as client:
        yield client


def _create_cv(api: TestClient, label: str = "Backend") -> str:
    response = api.post("/api/cvs", json={"label": label})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _upload(api: TestClient, cv_id: str, data: bytes | None = None) -> Any:
    payload = data if data is not None else build_docx()
    return api.post(
        f"/api/cvs/{cv_id}/versions",
        files={"file": ("cv.docx", payload, "application/octet-stream")},
        data={"note": "first upload"},
    )


def test_create_and_list_cvs(api: TestClient) -> None:
    cv_id = _create_cv(api, "Platform")

    listed = api.get("/api/cvs").json()

    assert listed["total"] == 1
    assert listed["items"][0]["id"] == cv_id
    assert listed["items"][0]["version_count"] == 0
    assert listed["items"][0]["latest_version_id"] is None


def test_label_length_is_enforced(api: TestClient) -> None:
    response = api.post("/api/cvs", json={"label": "x" * 61})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_upload_returns_metadata_and_warnings(api: TestClient) -> None:
    cv_id = _create_cv(api)

    response = _upload(api, cv_id)

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["version_no"] == 1
    assert body["warnings"] == ["no_sections_detected"]
    assert body["sections"] == ["other", "summary"]
    assert body["redaction"] == {"EMAIL": 1, "PHONE": 1, "ADDRESS": 1}
    assert "text" not in body


def test_no_pii_reaches_storage(api: TestClient, subject_container: Container) -> None:
    cv_id = _create_cv(api)
    version_id = _upload(api, cv_id).json()["id"]

    with subject_container.session_factory() as session:
        version = queries.get_version(session, version_id)
        assert version is not None
        assert "rina.pratama@example.com" not in version.redacted_text
        assert "812-3456-7890" not in version.redacted_text
        assert "Jl. Melati" not in version.redacted_text


def test_parser_view_returns_the_stored_text_byte_for_byte(
    api: TestClient, subject_container: Container
) -> None:
    cv_id = _create_cv(api)
    version_id = _upload(api, cv_id).json()["id"]

    view = api.get(f"/api/cv-versions/{version_id}/parser-view")

    assert view.status_code == 200
    with subject_container.session_factory() as session:
        version = queries.get_version(session, version_id)
        assert version is not None
        stored = version.redacted_text
    assert view.json()["text"].encode("utf-8") == stored.encode("utf-8")


def test_hashes_are_the_stored_ones(api: TestClient, subject_container: Container) -> None:
    payload = build_docx()
    cv_id = _create_cv(api)
    body = _upload(api, cv_id, payload).json()

    assert body["file_sha256"] == hashlib.sha256(payload).hexdigest()
    with subject_container.session_factory() as session:
        version = queries.get_version(session, body["id"])
        assert version is not None
        expected = hashlib.sha256(version.redacted_text.encode("utf-8")).hexdigest()
    assert body["text_sha256"] == expected


def test_identical_file_is_a_conflict(api: TestClient) -> None:
    cv_id = _create_cv(api)
    first = _upload(api, cv_id).json()

    second = _upload(api, cv_id)

    assert second.status_code == 409
    error = second.json()
    assert error["code"] == "CONFLICT"
    assert error["details"]["version_id"] == first["id"]
    assert error["details"]["href"] == f"/api/cv-versions/{first['id']}"


def test_same_file_on_another_cv_is_allowed(api: TestClient) -> None:
    first_cv = _create_cv(api, "Backend")
    second_cv = _create_cv(api, "Platform")
    assert _upload(api, first_cv).status_code == 201

    assert _upload(api, second_cv).status_code == 201


def test_upload_is_stored_under_its_hash(api: TestClient, subject_container: Container) -> None:
    payload = build_docx()
    cv_id = _create_cv(api)
    _upload(api, cv_id, payload)

    path = (
        subject_container.settings.data_dir
        / "uploads"
        / f"{hashlib.sha256(payload).hexdigest()}.docx"
    )
    assert path.read_bytes() == payload


def test_oversized_upload_is_rejected(
    schema: Engine, settings: Settings, clock: FixedClock
) -> None:
    small = settings.model_copy(update={"upload_max_bytes": 512})
    container = build_container(
        small,
        engine=schema,
        secret_store=InMemorySecretStore(),
        clock=clock,
        document_parser=FakeDocumentParser(parsed=PARSED),
    )
    with TestClient(create_app(container), base_url="http://127.0.0.1") as api:
        cv_id = _create_cv(api)
        response = _upload(api, cv_id, build_docx() * 4)

    assert response.status_code == 413
    assert response.json()["code"] == "UPLOAD_TOO_LARGE"


def test_unknown_extension_is_rejected(api: TestClient) -> None:
    cv_id = _create_cv(api)

    response = api.post(
        f"/api/cvs/{cv_id}/versions",
        files={"file": ("cv.txt", b"plain text", "text/plain")},
    )

    assert response.status_code == 422
    assert response.json()["code"] == "UPLOAD_INVALID"


def test_missing_cv_is_not_found(api: TestClient) -> None:
    response = _upload(api, "does-not-exist")

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_parse_failure_stores_nothing(
    settings: Settings, schema: Engine, secret_store: InMemorySecretStore, clock: FixedClock
) -> None:
    container = build_container(
        settings,
        engine=schema,
        secret_store=secret_store,
        clock=clock,
        document_parser=FakeDocumentParser(error="parser timed out"),
    )
    with TestClient(create_app(container), base_url="http://127.0.0.1") as api:
        cv_id = _create_cv(api)
        response = _upload(api, cv_id)
        listed = api.get("/api/cvs").json()

    assert response.status_code == 422
    assert response.json()["code"] == "CV_PARSE_FAILED"
    assert listed["items"][0]["version_count"] == 0


def test_empty_text_is_low_yield(
    settings: Settings, schema: Engine, secret_store: InMemorySecretStore, clock: FixedClock
) -> None:
    container = build_container(
        settings,
        engine=schema,
        secret_store=secret_store,
        clock=clock,
        document_parser=FakeDocumentParser(
            parsed=ParsedCv(text="   \n\n  ", warnings=["no_text_layer"])
        ),
    )
    with TestClient(create_app(container), base_url="http://127.0.0.1") as api:
        cv_id = _create_cv(api)
        response = _upload(api, cv_id)

    assert response.status_code == 422
    assert response.json()["code"] == "CV_PARSE_LOW_YIELD"


def test_impact_counts_versions(api: TestClient) -> None:
    cv_id = _create_cv(api)
    _upload(api, cv_id)

    impact = api.get(f"/api/cvs/{cv_id}/impact").json()

    assert impact == {"cv_id": cv_id, "version_count": 1, "analysis_count": 0}


def test_unknown_version_and_view_are_not_found(api: TestClient) -> None:
    assert api.get("/api/cv-versions/nope").status_code == 404
    assert api.get("/api/cv-versions/nope/parser-view").status_code == 404


def test_version_uploaded_at_uses_the_injected_clock(api: TestClient, fixed_now: datetime) -> None:
    cv_id = _create_cv(api)

    body = _upload(api, cv_id).json()

    assert datetime.fromisoformat(body["uploaded_at"]) == fixed_now

