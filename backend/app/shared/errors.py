"""Stable error codes and the single JSON error envelope.

Every failure path in the API returns `{code, message, details, request_id}`.
Provider exceptions never reach a router; they are mapped to an AppError first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

STATUS_BY_CODE: dict[str, int] = {
    "VALIDATION_ERROR": 422,
    "NOT_FOUND": 404,
    "CONFLICT": 409,
    "BAD_REQUEST": 400,
    "UNAUTHORIZED": 401,
    "DB_UNAVAILABLE": 503,
    "INTERNAL_ERROR": 500,
    "FETCH_HOST_BLOCKED": 400,
    "FETCH_URL_INVALID": 400,
    "FETCH_FAILED": 502,
    "LLM_TIMEOUT": 504,
    "LLM_RATE_LIMIT": 429,
    "LLM_AUTH": 502,
    "LLM_SCHEMA_INVALID": 502,
    "LLM_UNAVAILABLE": 502,
    "GMAIL_AUTH_EXPIRED": 401,
    "GMAIL_NOT_CONNECTED": 409,
    "ALERT_PARSE_FAILED": 422,
    "CV_PARSE_FAILED": 422,
    "CV_PARSE_LOW_YIELD": 422,
    "UPLOAD_INVALID": 422,
    "UPLOAD_TOO_LARGE": 413,
    "JD_NOT_FOUND": 422,
    "JD_MULTIPLE_JOBS": 422,
    "JD_TRUNCATED_SUSPECTED": 200,
    "TASK_STALE": 409,
    "BUDGET_EXCEEDED": 429,
    "COVER_NOTE_REJECTED": 422,
    "GUARD_BLOCKED": 409,
    "INVALID_DECISION": 422,
    "PURGE_CONFIRM_REQUIRED": 400,
    "BACKUP_UNSUPPORTED": 409,
    "BACKUP_FAILED": 500,
    "SECRET_STORE_UNAVAILABLE": 503,
}


@dataclass
class AppError(Exception):
    """A failure with a stable code. `details` must never contain CV or JD text."""

    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    status_code: int | None = None

    def __post_init__(self) -> None:
        Exception.__init__(self, self.message)
        if self.status_code is None:
            self.status_code = STATUS_BY_CODE.get(self.code, 500)

    def envelope(self, request_id: str | None) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "request_id": request_id,
        }
