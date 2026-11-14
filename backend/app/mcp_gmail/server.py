"""The stdio MCP server: exactly two read-only tools, and nothing else (PRD §8.10).

Tools never raise. They answer with `{"error": {"code", "message"}}` so the
backend can turn a failure into an actionable app error instead of a stack trace.
No tool takes a CV, a JD, or a prompt: this process only ever reads alert emails.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx
from mcp.server.fastmcp import FastMCP

from app.mcp_gmail import alert_parser, auth, gmail
from app.shared.secrets import KeyringSecretStore, SecretStoreUnavailable

MAX_LIMIT: Final = 50
MIN_LIMIT: Final = 1
CLIENT_SECRET_ENV: Final = "GMAIL_CLIENT_SECRET_PATH"  # noqa: S105 - a variable name
SENDER_ENV: Final = "GMAIL_ALERT_SENDER"
TIMEOUT_SECONDS: Final = 30.0

mcp = FastMCP("cv-fit-gmail")


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat()


def _failure(code: str, message: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": message}}


def _moment(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("since must be an ISO 8601 timestamp") from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


@contextmanager
def _reader() -> Iterator[gmail.GmailReader]:
    secret_path = os.environ.get(CLIENT_SECRET_ENV)
    if not secret_path:
        raise gmail.GmailError(f"{CLIENT_SECRET_ENV} is not set.")
    config = gmail.load_client_config(Path(secret_path))
    refresh_token = auth.load_refresh_token(KeyringSecretStore())
    if not refresh_token:
        raise gmail.GmailError("No Gmail token yet. Run: python -m app.mcp_gmail auth")
    with httpx.Client(timeout=TIMEOUT_SECONDS) as http:
        yield gmail.GmailReader(
            config=config,
            refresh_token=refresh_token,
            http=http,
            sender=os.environ.get(SENDER_ENV) or gmail.DEFAULT_ALERT_SENDER,
        )


def _tool_error(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, (gmail.GmailError, auth.AuthError)):
        return _failure(exc.code, str(exc))
    if isinstance(exc, SecretStoreUnavailable):
        return _failure("GMAIL_NOT_CONNECTED", "The OS keychain is locked.")
    return _failure("GMAIL_NOT_CONNECTED", "The Gmail helper hit an unexpected error.")


@mcp.tool()
def list_job_alerts(since: str | None = None, limit: int = 25) -> dict[str, Any]:
    """List job-alert emails from the configured alert sender, newest first.

    `since` is an ISO 8601 timestamp; omit it to look back 30 days. Returns
    message ids and received times only - never message bodies.
    """
    if not MIN_LIMIT <= limit <= MAX_LIMIT:
        return _failure("VALIDATION_ERROR", f"limit must be between {MIN_LIMIT} and {MAX_LIMIT}")
    try:
        moment = _moment(since)
        with _reader() as reader:
            found = reader.list_alerts(since=moment, limit=limit)
    except Exception as exc:  # noqa: BLE001 - tools answer, they do not raise
        return _tool_error(exc)
    return {
        "messages": [
            {"message_id": message_id, "received_at": _iso(received_at)}
            for message_id, received_at in found
        ]
    }


@mcp.tool()
def get_job_alert(message_id: str) -> dict[str, Any]:
    """Parse one alert email into job cards.

    An unrecognised layout comes back as a warning naming the message, so the
    backend can report a parse failure instead of silently dropping the email.
    """
    if not message_id.strip():
        return _failure("VALIDATION_ERROR", "message_id is required")
    try:
        with _reader() as reader:
            fetched = reader.fetch_alert(message_id.strip())
    except Exception as exc:  # noqa: BLE001 - tools answer, they do not raise
        return _tool_error(exc)
    parsed = alert_parser.parse_alert(subject=fetched.subject, body=fetched.body)
    warnings = list(parsed.warnings)
    if not parsed.recognized:
        warnings = [f"message {fetched.message_id}: {warning}" for warning in warnings]
    return {
        "message_id": fetched.message_id,
        "received_at": _iso(fetched.received_at),
        "layout": parsed.layout,
        "cards": [card.as_dict() for card in parsed.cards],
        "warnings": warnings,
    }


def _run_auth(argv: list[str]) -> int:
    secret_path = os.environ.get(CLIENT_SECRET_ENV)
    if not secret_path:
        print(f"{CLIENT_SECRET_ENV} is not set.", file=sys.stderr)
        return 2
    redirect_uri = argv[0] if argv else auth.DEFAULT_REDIRECT_URI
    try:
        config = gmail.load_client_config(Path(secret_path))
    except gmail.GmailError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        with httpx.Client(timeout=TIMEOUT_SECONDS) as http:
            auth.run_consent(
                client_id=config.client_id,
                client_secret=config.client_secret,
                redirect_uri=redirect_uri or config.redirect_uri,
                store=KeyringSecretStore(),
                http=http,
            )
    except (gmail.GmailError, auth.AuthError, SecretStoreUnavailable) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == "auth":
        return _run_auth(args[1:])
    if args and args[0] in {"-h", "--help"}:
        print("usage: python -m app.mcp_gmail [auth [redirect_uri]]")
        print("Without arguments it serves the two read-only tools over stdio.")
        return 0
    mcp.run(transport="stdio")
    return 0
