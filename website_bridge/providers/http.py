"""HTTP WebsiteProvider — the ONLY module in website_bridge that imports httpx."""

from __future__ import annotations

import asyncio
from urllib import robotparser
from urllib.parse import urlparse

import httpx

from shared.schemas import WebsiteFacts
from website_bridge.errors import RobotsDisallowedError, WebsiteFetchError
from website_bridge.extract import extract_facts


def robots_allows(url: str, user_agent: str) -> bool:
    """Check robots.txt for *url*. Unreachable robots.txt is treated as allowed (RFC)."""
    parsed = urlparse(url)
    parser = robotparser.RobotFileParser()
    parser.set_url(f"{parsed.scheme}://{parsed.netloc}/robots.txt")
    try:
        parser.read()
    except Exception:
        return True
    return parser.can_fetch(user_agent, url)


class HttpWebsiteProvider:
    def __init__(
        self,
        user_agent: str,
        timeout: float = 10.0,
        max_bytes: int = 2_000_000,
        max_redirects: int = 3,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._ua = user_agent
        self._timeout = timeout
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects
        self._transport = transport

    async def fetch_website_facts(self, url: str) -> WebsiteFacts:
        if not await asyncio.to_thread(robots_allows, url, self._ua):
            raise RobotsDisallowedError(url)

        client = httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            max_redirects=self._max_redirects,
            headers={"User-Agent": self._ua},
            transport=self._transport,
        )
        try:
            async with client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > self._max_bytes:
                            raise WebsiteFetchError(
                                f"Response exceeded {self._max_bytes} bytes: {url}"
                            )
                    final_url = str(response.url)
        except httpx.HTTPError as exc:
            raise WebsiteFetchError(f"Failed to fetch {url}: {exc}") from exc

        return extract_facts(bytes(body), final_url)
