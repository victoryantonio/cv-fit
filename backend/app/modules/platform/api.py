"""HTTP surface of the platform module: health, settings, data controls, Gmail."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from fastapi import APIRouter, Request

from app.modules.platform.data_controls import (
    BackupResult,
    DataSummary,
    PurgeRequest,
    PurgeResult,
)
from app.modules.platform.health import GMAIL_TOKEN_NAME
from app.modules.platform.settings_service import AppSettings
from app.shared.errors import AppError
from app.shared.secrets import SecretStoreUnavailable

if TYPE_CHECKING:
    from app.container import Container

router = APIRouter(prefix="/api", tags=["platform"])

#: D1: consent runs in the helper, so this process never holds an OAuth code.
AUTH_COMMAND: Final = "uv run python -m app.mcp_gmail auth"


def _container(request: Request) -> Container:
    return request.app.state.container


def _keyring_locked() -> AppError:
    return AppError(
        "SECRET_STORE_UNAVAILABLE",
        "The OS keychain is locked, so the Gmail token cannot be changed.",
        {},
    )


@router.get("/health")
async def health(request: Request, refresh: bool = False) -> dict[str, Any]:
    report = await _container(request).health.check(refresh=refresh)
    return report.as_dict()


@router.get("/settings")
def read_settings(request: Request) -> dict[str, Any]:
    return _container(request).settings_service.read()


@router.put("/settings")
def update_settings(payload: AppSettings, request: Request) -> dict[str, Any]:
    container = _container(request)
    updated = container.settings_service.update(payload)
    # A new key changes what health would say; do not make the user wait out the TTL.
    container.health.invalidate()
    return updated


@router.post("/gmail/connect")
async def connect_gmail(request: Request) -> dict[str, Any]:
    """Report Gmail state; consent itself happens in the helper (D1).

    Nothing here talks to Google: the helper owns the credential boundary, and
    the two-tool MCP contract has no place for an OAuth round trip.
    """
    report = await _container(request).health.check()
    if report.gmail == "connected":
        return {"status": "connected", "command": None}
    raise AppError(
        "GMAIL_NOT_CONNECTED",
        "Gmail is not connected. Run the auth command, then retry.",
        {"status": report.gmail, "command": AUTH_COMMAND},
    )


@router.post("/gmail/disconnect")
def disconnect_gmail(request: Request) -> dict[str, Any]:
    """Remove the local token only. Consent itself belongs to the helper (D1)."""
    store = _container(request).secret_store
    try:
        if store.get(GMAIL_TOKEN_NAME) is None:
            return {"status": "not_connected"}
        store.delete(GMAIL_TOKEN_NAME)
    except SecretStoreUnavailable as exc:
        raise _keyring_locked() from exc
    return {"status": "not_connected"}


@router.get("/data", response_model=DataSummary)
def read_data_summary(request: Request) -> DataSummary:
    """What exists, so the purge dialog can name what it deletes."""
    return _container(request).data_controls.summary()


@router.get("/data/export")
def export_data(request: Request) -> dict[str, Any]:
    """The user's own rows, back to the user. Never logged, never sent to a model."""
    return _container(request).data_controls.export()


@router.post("/data/purge", response_model=PurgeResult)
def purge_data(payload: PurgeRequest, request: Request) -> PurgeResult:
    return _container(request).data_controls.purge(confirm=payload.confirm)


@router.post("/backup", response_model=BackupResult)
def create_backup(request: Request) -> BackupResult:
    return _container(request).data_controls.backup()
