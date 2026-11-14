"""Data controls (FR-26): what exists, one export, a backup, and a purge.

This module works on the schema instead of on other modules' ORM classes. A
purge has to reach every table, and platform may not import analysis, cvs or
jobs; walking `Base.metadata` is the one view that covers all of them.

Settings survive a purge on purpose: they are configuration, not the user's
data, and silently wiping the model config in a "delete my data" action would
be a surprise. The UI says so before it asks for confirmation.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Table, delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db import Base, session_scope
from app.shared.clock import Clock
from app.shared.errors import AppError

PURGE_CONFIRMATION = "DELETE"
KEPT_IN_A_PURGE: frozenset[str] = frozenset({"app_setting"})


class DiskUsage(BaseModel):
    path: str
    files: int
    bytes: int


class BackupListing(BaseModel):
    directory: str
    files: int
    latest: str | None


class DataSummary(BaseModel):
    counts: dict[str, int]
    total_rows: int
    database: DiskUsage
    uploads: DiskUsage
    backups: BackupListing


class BackupResult(BaseModel):
    path: str
    bytes: int


class PurgeResult(BaseModel):
    deleted: dict[str, int]
    uploads_deleted: int


class PurgeRequest(BaseModel):
    confirm: str


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value


def _usage(directory: Path) -> DiskUsage:
    files = 0
    total = 0
    if directory.is_dir():
        for path in directory.iterdir():
            if path.is_file():
                files += 1
                total += path.stat().st_size
    return DiskUsage(path=str(directory), files=files, bytes=total)


def _free_path(directory: Path, stem: str) -> Path:
    """Two backups in the same second must not overwrite each other."""
    path = directory / f"{stem}.db"
    suffix = 1
    while path.exists():
        path = directory / f"{stem}-{suffix}.db"
        suffix += 1
    return path


def _purgeable() -> list[Table]:
    return [table for table in Base.metadata.sorted_tables if table.name not in KEPT_IN_A_PURGE]


class DataControlsService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        engine: Engine,
        settings: Settings,
        clock: Clock,
    ) -> None:
        self._session_factory = session_factory
        self._engine = engine
        self._settings = settings
        self._clock = clock

    def summary(self) -> DataSummary:
        with self._session_factory() as session:
            counts = {
                table.name: int(
                    session.execute(select(func.count()).select_from(table)).scalar_one()
                )
                for table in Base.metadata.sorted_tables
            }
        backups = self._settings.data_dir / "backups"
        written = sorted(path.name for path in backups.glob("*.db")) if backups.is_dir() else []
        database_path = self._sqlite_path()
        return DataSummary(
            counts=counts,
            total_rows=sum(counts.values()),
            database=DiskUsage(
                path=str(database_path) if database_path else "",
                files=1 if database_path and database_path.exists() else 0,
                bytes=database_path.stat().st_size
                if database_path and database_path.exists()
                else 0,
            ),
            uploads=_usage(self._settings.data_dir / "uploads"),
            backups=BackupListing(
                directory=str(backups),
                files=len(written),
                latest=written[-1] if written else None,
            ),
        )

    def export(self) -> dict[str, Any]:
        """Every row, as plain JSON. This file contains CV and job text."""
        tables: dict[str, list[dict[str, Any]]] = {}
        with self._session_factory() as session:
            for table in Base.metadata.sorted_tables:
                rows = session.execute(select(table)).mappings().all()
                tables[table.name] = [
                    {key: _json_safe(value) for key, value in row.items()} for row in rows
                ]
        return {"exported_at": self._clock.now().isoformat(), "tables": tables}

    def backup(self) -> BackupResult:
        """SQLite's own `.backup`, so WAL content is included and the file is consistent."""
        source = self._sqlite_path()
        if source is None:
            raise AppError(
                "BACKUP_UNSUPPORTED",
                "Backups are only implemented for the local SQLite file.",
                {"backend": self._engine.url.get_backend_name()},
            )
        if not source.exists():
            raise AppError(
                "BACKUP_FAILED",
                "The database file was not found, so there is nothing to copy.",
                {},
            )
        directory = self._settings.data_dir / "backups"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = self._clock.now().strftime("%Y%m%d-%H%M%S")
        target = _free_path(directory, f"app-{stamp}")
        try:
            origin = sqlite3.connect(source)
            try:
                copy = sqlite3.connect(target)
                try:
                    origin.backup(copy)
                finally:
                    copy.close()
            finally:
                origin.close()
        except sqlite3.Error as exc:
            raise AppError(
                "BACKUP_FAILED",
                "The backup could not be written. Check free space in the data folder.",
                {"reason": type(exc).__name__},
            ) from exc
        return BackupResult(path=str(target), bytes=target.stat().st_size)

    def purge(self, *, confirm: str) -> PurgeResult:
        if confirm.strip() != PURGE_CONFIRMATION:
            raise AppError(
                "PURGE_CONFIRM_REQUIRED",
                f"Type {PURGE_CONFIRMATION} to confirm that this data will be deleted.",
                {"expected": PURGE_CONFIRMATION},
            )
        deleted: dict[str, int] = {}
        with session_scope(self._session_factory) as session:
            # Reverse sorted order: children before the rows they point at.
            for table in reversed(_purgeable()):
                result = session.execute(delete(table))
                deleted[table.name] = max(result.rowcount or 0, 0)
        return PurgeResult(deleted=deleted, uploads_deleted=self._clear_uploads())

    def _clear_uploads(self) -> int:
        directory = self._settings.data_dir / "uploads"
        if not directory.is_dir():
            return 0
        removed = 0
        for path in directory.iterdir():
            if path.is_file():
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def _sqlite_path(self) -> Path | None:
        url = self._engine.url
        if url.get_backend_name() != "sqlite" or not url.database:
            return None
        return Path(url.database).resolve()
