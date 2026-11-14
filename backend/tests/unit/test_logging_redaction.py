"""Content must not reach the logs, even when a call site passes it by mistake."""

from __future__ import annotations

import io
import json
import logging

from app.shared.logging import ALLOWED_FIELDS, JsonFormatter, get_logger, task_id_var

CV_TEXT = "Jane Doe, jane.doe@example.com, +62 812 3456 7890, Staff Engineer at Acme"
JD_TEXT = "We need a Staff Backend Engineer with 8 years of Go experience."


def _capture(messages: list[tuple[str, dict[str, object]]]) -> str:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = get_logger("cv-fit.test")
    logger.handlers[:] = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for event, extra in messages:
        logger.info(event, extra=extra)
    return stream.getvalue()


def test_content_fields_are_dropped() -> None:
    output = _capture(
        [
            ("cv_parsed", {"cv_text": CV_TEXT, "jd_text": JD_TEXT}),
            ("jd_captured", {"raw_text": JD_TEXT, "email_body": JD_TEXT}),
        ]
    )

    assert CV_TEXT not in output
    assert JD_TEXT not in output
    assert "jane.doe@example.com" not in output
    for line in output.splitlines():
        payload = json.loads(line)
        assert set(payload) <= ALLOWED_FIELDS


def test_whitelisted_fields_survive() -> None:
    token = task_id_var.set("task-123")
    try:
        output = _capture([("match_step", {"outcome": "ok", "latency_ms": 42})])
    finally:
        task_id_var.reset(token)

    payload = json.loads(output.strip())
    assert payload["event"] == "match_step"
    assert payload["task_id"] == "task-123"
    assert payload["outcome"] == "ok"
    assert payload["latency_ms"] == 42


def test_output_is_one_json_object_per_line() -> None:
    output = _capture([("first", {}), ("second", {})])
    events = [json.loads(line)["event"] for line in output.splitlines()]
    assert events == ["first", "second"]
