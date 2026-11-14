"""Structured logging with a closed field whitelist.

The formatter builds its payload from an explicit list of fields. Any extra
attribute on a log record is dropped, so content cannot leak into logs even if
a future call site passes it by mistake.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
task_id_var: ContextVar[str | None] = ContextVar("task_id", default=None)
step_var: ContextVar[str | None] = ContextVar("step", default=None)

_CONTEXT_FIELDS: dict[str, ContextVar[str | None]] = {
    "request_id": request_id_var,
    "task_id": task_id_var,
    "step": step_var,
}
_METRIC_FIELDS = ("outcome", "latency_ms", "tokens_in", "tokens_out")

# Everything the formatter is allowed to emit besides ts/level/event.
ALLOWED_FIELDS = frozenset({"ts", "level", "event", *_CONTEXT_FIELDS, *_METRIC_FIELDS})


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "event": record.getMessage(),
        }
        for name, var in _CONTEXT_FIELDS.items():
            value = getattr(record, name, None)
            if value is None:
                value = var.get()
            if value is not None:
                payload[name] = value
        for name in _METRIC_FIELDS:
            value = getattr(record, name, None)
            if value is not None:
                payload[name] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
