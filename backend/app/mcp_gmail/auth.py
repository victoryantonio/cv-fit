"""OAuth2 for the helper: consent once, refresh forever, token in the keychain.

The consent step is a paste-the-redirect-URL flow on purpose: no local callback
server, no thread, and it works the same whether the browser is here or not.

`TOKEN_NAME` must match `GMAIL_TOKEN_NAME` in `app.modules.platform.health`, so
"connected" means the same thing to the health check and to this helper.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx

from app.shared.secrets import SecretStore

TOKEN_NAME: Final = "gmail_token"  # noqa: S105 - a keychain key, not a secret
TOKEN_URL: Final = "https://oauth2.googleapis.com/token"  # noqa: S105 - a URL, not a secret
AUTH_URL: Final = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPES: Final[tuple[str, ...]] = ("https://www.googleapis.com/auth/gmail.readonly",)
DEFAULT_REDIRECT_URI: Final = "http://127.0.0.1:8765/"
REFRESH_MARGIN: Final = timedelta(seconds=60)


class AuthError(Exception):
    """Consent or refresh failed; `code` is the app's error code for it."""

    def __init__(self, message: str, *, code: str = "GMAIL_NOT_CONNECTED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class AccessToken:
    value: str
    expires_at: datetime


def authorization_url(client_id: str, *, redirect_uri: str, state: str | None = None) -> str:
    query = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "state": state or secrets.token_urlsafe(16),
    }
    return f"{AUTH_URL}?{urlencode(query)}"


def extract_code(answer: str) -> str:
    """Accept a pasted redirect URL or a bare code."""
    value = answer.strip()
    if not value:
        raise AuthError("No authorisation code was given.")
    if "code=" in value:
        found = parse_qs(urlsplit(value).query).get("code")
        if found and found[0]:
            return found[0].strip()
        raise AuthError("That URL has no code in it.")
    return value


def _post_token(client: httpx.Client, data: dict[str, str]) -> dict[str, Any]:
    try:
        response = client.post(TOKEN_URL, data=data)
    except httpx.HTTPError as exc:
        raise AuthError("Could not reach Google's token endpoint.") from exc
    if response.status_code >= 400:
        raise AuthError("Google rejected the token request.", code="GMAIL_AUTH_EXPIRED")
    try:
        payload = response.json()
    except ValueError as exc:
        raise AuthError("Google's token endpoint answered with something else.") from exc
    if not isinstance(payload, dict) or not payload.get("access_token"):
        raise AuthError("Google's token response has no access token.")
    return payload


def exchange_code(
    *, client_id: str, client_secret: str, code: str, redirect_uri: str, http: httpx.Client
) -> str:
    """Trade the consent code for a refresh token, which is the durable part."""
    payload = _post_token(
        http,
        {
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
    )
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise AuthError("Google returned no refresh token. Revoke the app's access and try again.")
    return str(refresh_token)


def refresh_access_token(
    *,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    http: httpx.Client,
    now: Callable[[], datetime] | None = None,
) -> AccessToken:
    payload = _post_token(
        http,
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
    )
    moment = now() if now is not None else datetime.now(UTC)
    lifetime = int(payload.get("expires_in") or 3600)
    return AccessToken(
        value=str(payload["access_token"]),
        expires_at=moment + timedelta(seconds=max(lifetime - REFRESH_MARGIN.total_seconds(), 30)),
    )


def load_refresh_token(store: SecretStore) -> str | None:
    value = store.get(TOKEN_NAME)
    return value or None


def save_refresh_token(store: SecretStore, token: str) -> None:
    store.set(TOKEN_NAME, token)


def run_consent(
    *,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    store: SecretStore,
    http: httpx.Client,
    prompt: Callable[[str], str] = input,
    echo: Callable[[str], None] = print,
) -> str:
    url = authorization_url(client_id, redirect_uri=redirect_uri)
    echo("1. Open this URL in a browser signed in as the account that receives the alerts:")
    echo(url)
    echo("2. Approve read-only Gmail access, then paste the full redirect URL back here.")
    refresh_token = exchange_code(
        client_id=client_id,
        client_secret=client_secret,
        code=extract_code(str(prompt("redirect URL or code: "))),
        redirect_uri=redirect_uri,
        http=http,
    )
    save_refresh_token(store, refresh_token)
    echo("Stored the Gmail refresh token in the OS keychain.")
    return refresh_token
