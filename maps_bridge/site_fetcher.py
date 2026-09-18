"""Guarded website fetcher backing the fetch_site MCP tool.

The only network boundary for arbitrary, search-result-derived URLs
(invariant #5, ADR 0003). SSRF is handled in code rather than deployment
topology: http/https only, private/loopback/link-local addresses blocked
(re-checked on every redirect hop), hard response-size and time limits.
No HTML parsing beyond tag-stripped plain text; no LLM work here.
"""

import asyncio
import ipaddress
import socket
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from maps_bridge.errors import SiteFetchError
from shared.schemas import FetchedSite

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_RESPONSE_BYTES = 2_000_000
_MAX_REDIRECTS = 5
_REQUEST_TIMEOUT_SECONDS = 10.0
_TOTAL_TIMEOUT_SECONDS = 20.0

_SKIPPED_TAGS = frozenset({"script", "style", "head"})

_MOCK_FIXTURE_PATH = Path(__file__).parent / "fixtures" / "recorded" / "sites" / "generic.html"


class _TextExtractor(HTMLParser):
    """Strips tags, discarding script/style/head content."""

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIPPED_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIPPED_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._chunks.append(stripped)

    def text(self) -> str:
        return "\n".join(self._chunks)


def _html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def _resolve_public_ip(hostname: str) -> str:
    """Resolve hostname and return the first public address found.

    The returned address is later used verbatim as the connection target
    (see `_pin_to_ip`) rather than re-resolved by the HTTP client — letting
    the client do its own lookup would open a DNS-rebinding gap: an attacker
    whose DNS answer changes between this check and the actual connection
    could have this function see a public IP while the connection lands on
    a private one.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise SiteFetchError(f"Could not resolve host: {hostname!r}") from exc
    for info in infos:
        candidate = ipaddress.ip_address(info[4][0])
        if _is_public(candidate):
            return str(candidate)
    raise SiteFetchError(f"Refusing to fetch non-public address for host: {hostname!r}")


def _pin_to_ip(url: str, ip: str) -> str:
    """Rewrite url's host to the already-validated ip, so the HTTP client
    connects to exactly the address `_resolve_public_ip` approved."""
    parts = urlsplit(url)
    netloc = f"[{ip}]" if ":" in ip else ip
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path or "/", parts.query, parts.fragment))


async def _fetch_hop(
    url: str, *, client: httpx.AsyncClient, max_bytes: int
) -> tuple[str, FetchedSite] | tuple[str, None]:
    """Fetch one hop. Returns (redirect_target, None) or (final_url, FetchedSite)."""
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        raise SiteFetchError(f"Unsupported URL scheme: {parts.scheme!r}")
    if not parts.hostname:
        raise SiteFetchError(f"URL has no host: {url!r}")

    resolved_ip = await _resolve_public_ip(parts.hostname)
    pinned_url = _pin_to_ip(url, resolved_ip)
    headers = {"Host": parts.hostname}
    extensions = {"sni_hostname": parts.hostname} if parts.scheme == "https" else {}

    try:
        async with client.stream(
            "GET", pinned_url, headers=headers, extensions=extensions, follow_redirects=False
        ) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise SiteFetchError(f"Redirect with no Location header from {url!r}")
                return urljoin(url, location), None

            content_type = response.headers.get("content-type", "")
            if not content_type.split(";")[0].strip().startswith("text/html"):
                raise SiteFetchError(f"Unsupported content type {content_type!r} from {url!r}")

            content_length = response.headers.get("content-length")
            if content_length is not None:
                try:
                    declared_bytes = int(content_length)
                except ValueError as exc:
                    raise SiteFetchError(
                        f"Invalid Content-Length header {content_length!r} from {url!r}"
                    ) from exc
                if declared_bytes > max_bytes:
                    raise SiteFetchError(
                        f"Response too large ({declared_bytes} bytes) from {url!r}"
                    )

            body = bytearray()
            async for chunk in response.aiter_bytes():
                body.extend(chunk)
                if len(body) > max_bytes:
                    raise SiteFetchError(f"Response exceeded {max_bytes} bytes from {url!r}")

            encoding = response.encoding or "utf-8"
            text = _html_to_text(bytes(body).decode(encoding, errors="replace"))
            return url, FetchedSite(text=text, final_url=url)
    except httpx.TimeoutException as exc:
        raise SiteFetchError(f"Timed out fetching {url!r}") from exc
    except httpx.TransportError as exc:
        raise SiteFetchError(f"Network error fetching {url!r}: {exc}") from exc


async def _fetch_site_live(url: str, *, client: httpx.AsyncClient, max_bytes: int) -> FetchedSite:
    current_url = url
    for _ in range(_MAX_REDIRECTS + 1):
        current_url, result = await _fetch_hop(current_url, client=client, max_bytes=max_bytes)
        if result is not None:
            return result
    raise SiteFetchError(f"Too many redirects fetching {url!r}")


async def fetch_site_live(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
    max_bytes: int = _MAX_RESPONSE_BYTES,
    request_timeout: float = _REQUEST_TIMEOUT_SECONDS,
    total_timeout: float = _TOTAL_TIMEOUT_SECONDS,
) -> FetchedSite:
    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=request_timeout)
    try:
        try:
            return await asyncio.wait_for(
                _fetch_site_live(url, client=active_client, max_bytes=max_bytes),
                timeout=total_timeout,
            )
        except TimeoutError as exc:
            raise SiteFetchError(f"Timed out fetching {url!r}") from exc
    finally:
        if owns_client:
            await active_client.aclose()


async def fetch_site_mock(url: str) -> FetchedSite:
    """Recorded-content path — never touches the network (tests, demo mode)."""
    html = _MOCK_FIXTURE_PATH.read_text(encoding="utf-8")
    return FetchedSite(text=_html_to_text(html), final_url=url)
