"""A stand-in for the Gmail helper: canned payloads over the real MCP transport.

This exists so the backend's stdio adapter can be tested without Gmail
credentials, and so a helper-side error envelope can be exercised on demand.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("stub-alerts")

MESSAGES: list[dict[str, Any]] = [
    {"message_id": "m1", "received_at": "2025-01-02T09:00:00+00:00"},
    {"message_id": "m2", "received_at": "2025-01-01T09:00:00+00:00"},
]

CARDS: list[dict[str, Any]] = [
    {
        "title": "Senior AI Engineer",
        "company": "Westpac",
        "location": "Sydney, NSW",
        "url": "https://www.linkedin.com/comm/jobs/view/4453662232/",
    },
    {"title": "AI Engineer", "company": None, "location": None, "url": None},
]


@mcp.tool()
def list_job_alerts(since: str | None = None, limit: int = 25) -> dict[str, Any]:
    del since
    return {"messages": MESSAGES[:limit]}


@mcp.tool()
def get_job_alert(message_id: str) -> dict[str, Any]:
    if message_id == "boom":
        return {"error": {"code": "ALERT_PARSE_FAILED", "message": "unknown alert layout"}}
    if message_id == "missing":
        return {"error": {"code": "GMAIL_NOT_CONNECTED", "message": "no such message"}}
    return {
        "message_id": message_id,
        "received_at": "2025-01-02T09:00:00+00:00",
        "layout": "linkedin_job_alert_digest",
        "cards": CARDS,
        "warnings": [],
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
