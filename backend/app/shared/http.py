"""The only place an outbound URL is fetched.

Guarantees, in this order: the host is not on the blocklist, the resolved
addresses are public, and every redirect hop is checked again. A second HTTP
path would defeat this, so none exists.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from urllib.parse import urljoin, urlsplit

import httpx

from app.shared.errors import AppError

Resolver = Callable[[str, int], Sequence[str]]
DEFAULT_PORTS = {"http": 80, "https": 443}
MAX_REDIRECTS = 5
MAX_BYTES = 2_000_000


def _default_resolver(host: str, port: int) -> Sequence[str]:
    infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


def _host_matches(host: str, blocked: Sequence[str]) -> bool:
    for entry in blocked:
        normalized = entry.strip().lower().removeprefix("*.").strip(".")
        if normalized and (host == normalized or host.endswith("." + normalized)):
            return True
    return False


def _is_public(ip_text: str) -> bool:
    try:
        address = ipaddress.ip_address(ip_text)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return bool(address.is_global) and not address.is_multicast


def blocked_host_of(url: str, *, blocked_hosts: Sequence[str]) -> str | None:
    """The blocked host this URL would contact, or None.

    Pure string work: no DNS and no request, so a caller that only needs the
    blocklist rule (the model provider probe) does not pay for a resolution and
    is not refused a private address the way a user-supplied URL would be.
    """
    host = (urlsplit(url).hostname or "").lower().rstrip(".")
    return host if host and _host_matches(host, blocked_hosts) else None


def assert_host_allowed(
    url: str,
    *,
    blocked_hosts: Sequence[str],
    resolver: Resolver = _default_resolver,
) -> str:
    """Return the host when it may be contacted, otherwise raise AppError."""
    parts = urlsplit(url)
    if parts.scheme not in DEFAULT_PORTS:
        raise AppError("FETCH_URL_INVALID", "Only http and https URLs can be fetched.")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise AppError("FETCH_URL_INVALID", "The URL has no host.")
    if blocked_host_of(url, blocked_hosts=blocked_hosts):
        raise AppError("FETCH_HOST_BLOCKED", f"Host is on the blocklist: {host}")
    port = parts.port or DEFAULT_PORTS[parts.scheme]
    try:
        addresses = list(resolver(host, port))
    except OSError as exc:
        raise AppError("FETCH_FAILED", "The host could not be resolved.") from exc
    if not addresses:
        raise AppError("FETCH_FAILED", "The host could not be resolved.")
    for address in addresses:
        if not _is_public(address):
            raise AppError("FETCH_HOST_BLOCKED", f"Host resolves to a non-public address: {host}")
    return host


class SafeFetcher:
    def __init__(
        self,
        *,
        blocked_hosts: Sequence[str],
        client: httpx.AsyncClient | None = None,
        timeout_s: float = 10.0,
        max_bytes: int = MAX_BYTES,
        max_redirects: int = MAX_REDIRECTS,
        resolver: Resolver = _default_resolver,
    ) -> None:
        self._blocked_hosts = tuple(blocked_hosts)
        self._client = client
        self._timeout_s = timeout_s
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects
        self._resolver = resolver

    async def get_text(self, url: str) -> str:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout_s, follow_redirects=False)
        try:
            return await self._follow(client, url)
        except httpx.HTTPError as exc:
            raise AppError("FETCH_FAILED", "The request failed.") from exc
        finally:
            if owns_client:
                await client.aclose()

    async def _follow(self, client: httpx.AsyncClient, url: str) -> str:
        for _ in range(self._max_redirects + 1):
            assert_host_allowed(url, blocked_hosts=self._blocked_hosts, resolver=self._resolver)
            response = await self._request(client, url)
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise AppError("FETCH_FAILED", "Redirect without a location.")
                url = urljoin(url, location)
                continue
            if response.status_code >= 400:
                raise AppError("FETCH_FAILED", f"The page returned HTTP {response.status_code}.")
            return response.text
        raise AppError("FETCH_FAILED", "Too many redirects.")

    async def _request(self, client: httpx.AsyncClient, url: str) -> httpx.Response:
        async with client.stream(
            "GET",
            url,
            headers={"User-Agent": "cv-fit/0.1"},
            follow_redirects=False,
        ) as response:
            chunks: list[bytes] = []
            size = 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > self._max_bytes:
                    raise AppError("FETCH_FAILED", "The page is larger than the limit.")
                chunks.append(chunk)
            return httpx.Response(
                status_code=response.status_code,
                headers=response.headers,
                content=b"".join(chunks),
                request=response.request,
            )
