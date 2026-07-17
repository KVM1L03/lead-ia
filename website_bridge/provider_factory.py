"""Provider singleton for website_bridge — importable without starting the server."""

from __future__ import annotations

from functools import lru_cache

from website_bridge.cache import CachingWebsiteProvider, InMemoryCache
from website_bridge.config import settings
from website_bridge.providers import WebsiteProvider


@lru_cache(maxsize=4)
def get_provider(provider_name: str | None = None) -> WebsiteProvider:
    """Return a WebsiteProvider (mock or http), wrapped in a per-domain cache."""
    active = provider_name or settings.WEBSITE_PROVIDER
    inner: WebsiteProvider
    if active == "mock":
        from website_bridge.providers.mock import MockWebsiteProvider

        inner = MockWebsiteProvider()
    elif active == "http":
        from website_bridge.providers.http import HttpWebsiteProvider

        inner = HttpWebsiteProvider(
            user_agent=settings.WEBSITE_USER_AGENT,
            timeout=settings.WEBSITE_FETCH_TIMEOUT,
            max_bytes=settings.WEBSITE_MAX_BYTES,
            max_redirects=settings.WEBSITE_MAX_REDIRECTS,
        )
    else:
        raise NotImplementedError(f"Unknown provider: {active!r}")

    return CachingWebsiteProvider(inner, InMemoryCache(ttl=settings.WEBSITE_CACHE_TTL))
