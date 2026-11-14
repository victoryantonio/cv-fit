"""Queries for the platform module. No business rules here."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.platform.models import AppSetting


def get_setting(session: Session, key: str) -> Any | None:
    row = session.get(AppSetting, key)
    return None if row is None else row.value_json


def get_all_settings(session: Session) -> dict[str, Any]:
    rows = session.execute(select(AppSetting)).scalars().all()
    return {row.key: row.value_json for row in rows}


def put_setting(session: Session, key: str, value: Any) -> None:
    row = session.get(AppSetting, key)
    if row is None:
        session.add(AppSetting(key=key, value_json=value))
    else:
        row.value_json = value
