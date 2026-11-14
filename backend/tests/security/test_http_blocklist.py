"""The one HTTP path must refuse LinkedIn, private addresses and innocent redirects."""

from __future__ import annotations

from collections.abc import Sequence

import httpx
import pytest

from app.shared.errors import AppError
from app.shared.http import Resolver, SafeFetcher, assert_host_allowed

BLOCKED = ("linkedin.com",)


def _resolver_for(mapping: dict[str, list[str]]) -> Resolver:
    def resolve(host: str, _port: int) -> Sequence[str]:
        return mapping.get(host, ["93.184.216.34"])

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "https://linkedin.com/jobs/view/1",
        "https://www.linkedin.com/jobs/view/1",
        "https://id.linkedin.com/jobs/view/1",
        "https://LINKEDIN.com./jobs",
    ],
)
def test_blocklisted_hosts_are_refused(url: str) -> None:
    with pytest.raises(AppError) as excinfo:
        assert_host_allowed(url, blocked_hosts=BLOCKED, resolver=_resolver_for({}))
    assert excinfo.value.code == "FETCH_HOST_BLOCKED"


@pytest.mark.parametrize(
    "address",
    ["127.0.0.1", "10.0.0.5", "192.168.1.10", "169.254.169.254", "::1", "::ffff:127.0.0.1"],
)
def test_non_public_addresses_are_refused(address: str) -> None:
    resolver = _resolver_for({"jobs.example.com": [address]})
    with pytest.raises(AppError) as excinfo:
        assert_host_allowed(
            "https://jobs.example.com/post", blocked_hosts=BLOCKED, resolver=resolver
        )
    assert excinfo.value.code == "FETCH_HOST_BLOCKED"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "not a url"])
def test_non_http_schemes_are_refused(url: str) -> None:
    with pytest.raises(AppError) as excinfo:
        assert_host_allowed(url, blocked_hosts=BLOCKED, resolver=_resolver_for({}))
    assert excinfo.value.code == "FETCH_URL_INVALID"


def test_public_host_is_allowed() -> None:
    host = assert_host_allowed(
        "https://jobs.example.com/post", blocked_hosts=BLOCKED, resolver=_resolver_for({})
    )
    assert host == "jobs.example.com"


async def test_redirect_hop_to_blocked_host_is_refused() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "https://www.linkedin.com/jobs/1"})

    fetcher = SafeFetcher(
        blocked_hosts=BLOCKED,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        resolver=_resolver_for({}),
    )
    with pytest.raises(AppError) as excinfo:
        await fetcher.get_text("https://jobs.example.com/redirect")
    assert excinfo.value.code == "FETCH_HOST_BLOCKED"
    assert seen == ["https://jobs.example.com/redirect"]


async def test_oversized_body_is_refused() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 4096)

    fetcher = SafeFetcher(
        blocked_hosts=BLOCKED,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        max_bytes=1024,
        resolver=_resolver_for({}),
    )
    with pytest.raises(AppError) as excinfo:
        await fetcher.get_text("https://jobs.example.com/big")
    assert excinfo.value.code == "FETCH_FAILED"


async def test_text_is_returned_for_a_public_page() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="We are hiring a Backend Engineer.")

    fetcher = SafeFetcher(
        blocked_hosts=BLOCKED,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        resolver=_resolver_for({}),
    )
    assert "Backend Engineer" in await fetcher.get_text("https://jobs.example.com/p")
