"""Read-only Gmail access over plain HTTPS.

Two endpoints and a refresh call are all this needs, so there is no Google SDK
here: one HTTP client, fixed hosts, and every byte of it testable without a
network. Nothing in this file touches LinkedIn; it reads the alert emails the
user already receives.
"""

from __future__ import annotations

import base64
import binascii
import html
import json
import quopri
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

import httpx

from app.mcp_gmail import auth

API_BASE: Final = "https://gmail.googleapis.com/gmail/v1"
DEFAULT_ALERT_SENDER: Final = "jobalerts-noreply@linkedin.com"
MAX_BODY_CHARS: Final = 200_000
DEFAULT_LOOKBACK_DAYS: Final = 30

_BLOCK_TAG = re.compile(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h[1-6]>")
_ANY_TAG = re.compile(r"<[^>]+>")
_QUOTED_PRINTABLE = re.compile(r"=[0-9A-F]{2}", re.IGNORECASE)
_SPACES = re.compile(r"[ \t\u00a0]+")
_BLANK_LINES = re.compile(r"\n{3,}")


class GmailError(Exception):
    """A Gmail call failed; `code` is the app's error code for it."""

    def __init__(self, message: str, *, code: str = "GMAIL_NOT_CONNECTED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class ClientConfig:
    client_id: str
    client_secret: str
    redirect_uri: str = auth.DEFAULT_REDIRECT_URI


@dataclass(frozen=True, slots=True)
class FetchedAlert:
    message_id: str
    received_at: datetime
    subject: str
    sender: str
    body: str


def load_client_config(path: Path) -> ClientConfig:
    """Read the OAuth client Google Cloud Console downloads."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GmailError(f"Gmail client secret not found at {path.name}.") from exc
    except (OSError, ValueError) as exc:
        raise GmailError("Gmail client secret is not readable JSON.") from exc
    block = raw.get("installed") or raw.get("web") or {}
    client_id = block.get("client_id")
    client_secret = block.get("client_secret")
    if not client_id or not client_secret:
        raise GmailError("Gmail client secret is missing client_id/client_secret.")
    redirects = block.get("redirect_uris") or []
    redirect_uri = redirects[0] if redirects else auth.DEFAULT_REDIRECT_URI
    return ClientConfig(str(client_id), str(client_secret), str(redirect_uri))


def _decode_part(part: dict[str, Any]) -> str | None:
    data = (part.get("body") or {}).get("data")
    if not data:
        return None
    try:
        raw = base64.urlsafe_b64decode(str(data) + "=" * (-len(str(data)) % 4))
    except (binascii.Error, ValueError):
        return None
    text = raw.decode("utf-8", "replace")
    if "=\r\n" in text or "=\n" in text or _QUOTED_PRINTABLE.search(text[:4000]):
        text = quopri.decodestring(text.encode("utf-8", "replace")).decode("utf-8", "replace")
    return text


def _walk(payload: dict[str, Any]) -> list[dict[str, Any]]:
    parts = [payload]
    for child in payload.get("parts") or []:
        if isinstance(child, dict):
            parts.extend(_walk(child))
    return parts


def html_to_text(markup: str) -> str:
    text = _BLOCK_TAG.sub("\n", markup)
    text = _ANY_TAG.sub("", text)
    text = html.unescape(text)
    text = _SPACES.sub(" ", text)
    return _BLANK_LINES.sub("\n\n", text).strip()


def _body_text(payload: dict[str, Any]) -> str:
    plain: list[str] = []
    rich: list[str] = []
    for part in _walk(payload):
        mime = str(part.get("mimeType") or "")
        if mime == "text/plain":
            decoded = _decode_part(part)
            if decoded:
                plain.append(decoded)
        elif mime == "text/html":
            decoded = _decode_part(part)
            if decoded:
                rich.append(decoded)
    if plain:
        return max(plain, key=len)
    if rich:
        return html_to_text(max(rich, key=len))
    return ""


def _headers(payload: dict[str, Any]) -> dict[str, str]:
    found: dict[str, str] = {}
    for header in payload.get("headers") or []:
        name = str(header.get("name") or "").lower()
        if name and name not in found:
            found[name] = str(header.get("value") or "")
    return found


def _parse_internal_date(value: Any) -> datetime:
    try:
        millis = int(str(value))
    except (TypeError, ValueError):
        return datetime.now(UTC)
    return datetime.fromtimestamp(millis / 1000, tz=UTC)


class GmailReader:
    """The two calls this app needs, each with an honest failure code."""

    def __init__(
        self,
        *,
        config: ClientConfig,
        refresh_token: str,
        http: httpx.Client,
        sender: str = DEFAULT_ALERT_SENDER,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._config = config
        self._refresh_token = refresh_token
        self._http = http
        self._sender = sender
        self._now = now or (lambda: datetime.now(UTC))
        self._access_token: str | None = None
        self._expires_at: datetime | None = None

    def _token(self) -> str:
        moment = self._now()
        if self._access_token and self._expires_at and moment < self._expires_at:
            return self._access_token
        token = auth.refresh_access_token(
            client_id=self._config.client_id,
            client_secret=self._config.client_secret,
            refresh_token=self._refresh_token,
            http=self._http,
            now=self._now,
        )
        self._access_token = token.value
        self._expires_at = token.expires_at
        return token.value

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            response = self._http.get(
                f"{API_BASE}{path}",
                params=params or {},
                headers={"Authorization": f"Bearer {self._token()}"},
            )
        except httpx.HTTPError as exc:
            raise GmailError("Could not reach Gmail.") from exc
        if response.status_code in {401, 403}:
            raise GmailError("Gmail rejected the stored token.", code="GMAIL_AUTH_EXPIRED")
        if response.status_code >= 400:
            raise GmailError(f"Gmail returned HTTP {response.status_code}.")
        try:
            payload = response.json()
        except ValueError as exc:
            raise GmailError("Gmail returned something that is not JSON.") from exc
        if not isinstance(payload, dict):
            raise GmailError("Gmail returned something that is not JSON.")
        return payload

    def list_alerts(
        self, *, since: datetime | None = None, limit: int = 25
    ) -> list[tuple[str, datetime]]:
        """Newest first. `received_at` costs one extra metadata call per message."""
        query = f"from:{self._sender}"
        if since is not None:
            query = f"{query} after:{int(since.timestamp())}"
        else:
            query = f"{query} newer_than:{DEFAULT_LOOKBACK_DAYS}d"
        listing = self._get("/users/me/messages", {"q": query, "maxResults": limit})
        found: list[tuple[str, datetime]] = []
        for entry in listing.get("messages") or []:
            message_id = str(entry.get("id") or "")
            if not message_id:
                continue
            meta = self._get(
                f"/users/me/messages/{message_id}",
                {"format": "metadata", "metadataHeaders": "Date"},
            )
            found.append((message_id, _parse_internal_date(meta.get("internalDate"))))
        return found[:limit]

    def fetch_alert(self, message_id: str) -> FetchedAlert:
        message = self._get(f"/users/me/messages/{message_id}", {"format": "full"})
        payload = message.get("payload") or {}
        headers = _headers(payload)
        return FetchedAlert(
            message_id=message_id,
            received_at=_parse_internal_date(message.get("internalDate")),
            subject=headers.get("subject", ""),
            sender=headers.get("from", ""),
            body=_body_text(payload)[:MAX_BODY_CHARS],
        )
