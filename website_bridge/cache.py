"""In-memory per-domain cache and transparent caching wrapper for WebsiteProvider."""

from __future__ import annotations

import time
from urllib.parse import urlparse

from shared.schemas import WebsiteFacts
from website_bridge.providers import WebsiteProvider


def _domain_key(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


class InMemoryCache:
    def __init__(self, ttl: int = 86400) -> None:
        self._ttl = ttl
        self._store: dict[str, tuple[float, WebsiteFacts]] = {}

    def get(self, domain: str) -> WebsiteFacts | None:
        entry = self._store.get(domain)
        if entry is None:
            return None
        created_at, facts = entry
        if time.time() - created_at > self._ttl:
            del self._store[domain]
            return None
        return facts

    def set(self, domain: str, facts: WebsiteFacts) -> None:
        self._store[domain] = (time.time(), facts)


class CachingWebsiteProvider:
    """Transparent per-domain caching layer around any WebsiteProvider."""

    def __init__(self, inner: WebsiteProvider, cache: InMemoryCache) -> None:
        self._inner = inner
        self._cache = cache

    async def fetch_website_facts(self, url: str) -> WebsiteFacts:
        key = _domain_key(url)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        facts = await self._inner.fetch_website_facts(url)
        self._cache.set(key, facts)
        return facts
