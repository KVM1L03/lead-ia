"""Tests for the guarded fetch_site implementation — no live HTTP.

Public-IP literals (e.g. 93.184.216.10) resolve via getaddrinfo without any
real DNS/network call, so guard-case tests stay hermetic.
"""

import httpx
import pytest

from maps_bridge.errors import SiteFetchError
from maps_bridge.site_fetcher import fetch_site_live, fetch_site_mock


class _StaticTransport(httpx.AsyncBaseTransport):
    """Returns one fixed response (or raises) for every request; counts calls."""

    def __init__(
        self,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        content: bytes = b"",
        raise_exc: Exception | None = None,
    ) -> None:
        self.call_count = 0
        self._status_code = status_code
        self._headers = headers or {}
        self._content = content
        self._raise_exc = raise_exc

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        if self._raise_exc is not None:
            raise self._raise_exc
        return httpx.Response(
            status_code=self._status_code, headers=self._headers, content=self._content
        )


def _client(transport: httpx.AsyncBaseTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=transport)


async def test_rejects_private_ip_without_any_network_call() -> None:
    transport = _StaticTransport()
    with pytest.raises(SiteFetchError, match="non-public"):
        await fetch_site_live("http://127.0.0.1/admin", client=_client(transport))
    assert transport.call_count == 0


async def test_rejects_link_local_metadata_address() -> None:
    transport = _StaticTransport()
    with pytest.raises(SiteFetchError, match="non-public"):
        await fetch_site_live("http://169.254.169.254/latest/meta-data/", client=_client(transport))
    assert transport.call_count == 0


async def test_rejects_non_http_scheme() -> None:
    with pytest.raises(SiteFetchError, match="scheme"):
        await fetch_site_live("ftp://93.184.216.10/")


async def test_rejects_redirect_to_private_ip() -> None:
    transport = _StaticTransport(status_code=302, headers={"location": "http://127.0.0.1/private"})
    with pytest.raises(SiteFetchError, match="non-public"):
        await fetch_site_live("http://93.184.216.10/", client=_client(transport))
    assert transport.call_count == 1


async def test_rejects_oversized_body_via_content_length_header() -> None:
    transport = _StaticTransport(
        headers={"content-type": "text/html", "content-length": "999999"},
        content=b"<html><body>hi</body></html>",
    )
    with pytest.raises(SiteFetchError, match=r"too large|exceeded"):
        await fetch_site_live("http://93.184.216.10/", client=_client(transport), max_bytes=10)


async def test_rejects_oversized_body_during_streaming_when_header_understates_size() -> None:
    class _LyingLengthTransport(httpx.AsyncBaseTransport):
        """Understates content-length so only the streaming cap can catch it."""

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            body = b"<html><body>" + b"x" * 1000 + b"</body></html>"
            return httpx.Response(
                status_code=200,
                headers={"content-type": "text/html", "content-length": "5"},
                content=body,
            )

    with pytest.raises(SiteFetchError, match="exceeded"):
        await fetch_site_live(
            "http://93.184.216.10/", client=_client(_LyingLengthTransport()), max_bytes=10
        )


async def test_rejects_non_html_content_type() -> None:
    transport = _StaticTransport(headers={"content-type": "application/pdf"}, content=b"%PDF-1.4")
    with pytest.raises(SiteFetchError, match="content type"):
        await fetch_site_live("http://93.184.216.10/", client=_client(transport))


async def test_rejects_invalid_content_length_header() -> None:
    transport = _StaticTransport(
        headers={"content-type": "text/html", "content-length": "not-a-number"},
        content=b"<html></html>",
    )
    with pytest.raises(SiteFetchError, match="Invalid Content-Length"):
        await fetch_site_live("http://93.184.216.10/", client=_client(transport))


async def test_pins_connection_to_resolved_ip_and_preserves_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DNS-rebinding guard: the HTTP client must connect to the exact address
    `_resolve_public_ip` validated, not re-resolve the hostname itself."""
    import maps_bridge.site_fetcher as site_fetcher

    async def _fake_resolve(hostname: str) -> str:
        assert hostname == "example.com"
        return "93.184.216.34"

    monkeypatch.setattr(site_fetcher, "_resolve_public_ip", _fake_resolve)

    class _CapturingTransport(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.last_request: httpx.Request | None = None

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.last_request = request
            return httpx.Response(
                status_code=200,
                headers={"content-type": "text/html"},
                content=b"<html><body>hi</body></html>",
            )

    transport = _CapturingTransport()
    result = await fetch_site_live("http://example.com/page", client=_client(transport))

    assert transport.last_request is not None
    assert transport.last_request.url.host == "93.184.216.34"
    assert transport.last_request.headers["host"] == "example.com"
    assert result.final_url == "http://example.com/page"


async def test_raises_on_timeout() -> None:
    transport = _StaticTransport(raise_exc=httpx.ReadTimeout("timed out"))
    with pytest.raises(SiteFetchError, match=r"[Tt]imed out"):
        await fetch_site_live("http://93.184.216.10/", client=_client(transport))


async def test_extracts_text_and_reports_final_url_after_redirect() -> None:
    class _RedirectThenPageTransport(httpx.AsyncBaseTransport):
        def __init__(self) -> None:
            self.call_count = 0

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.call_count += 1
            if self.call_count == 1:
                return httpx.Response(
                    status_code=301, headers={"location": "http://93.184.216.11/home"}
                )
            return httpx.Response(
                status_code=200,
                headers={"content-type": "text/html; charset=utf-8"},
                content=b"<html><head><style>.x{}</style></head>"
                b"<body><h1>Acme</h1><p>Contact us</p><script>evil()</script></body></html>",
            )

    transport = _RedirectThenPageTransport()
    result = await fetch_site_live("http://93.184.216.10/", client=_client(transport))
    assert result.final_url == "http://93.184.216.11/home"
    assert "Acme" in result.text
    assert "Contact us" in result.text
    assert "evil()" not in result.text
    assert transport.call_count == 2


async def test_fetch_site_mock_never_touches_network() -> None:
    result = await fetch_site_mock("https://example.com")
    assert result.final_url == "https://example.com"
    assert len(result.text) > 0
