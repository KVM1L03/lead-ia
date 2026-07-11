"""Provider singleton for maps_bridge — importable without starting the MCP server.

Importing this module does NOT start the FastMCP stdio loop. Safe to import from
ai_worker when MAPS_TRANSPORT=inline (provider runs in-process).
"""

from __future__ import annotations

from functools import lru_cache

from maps_bridge.config import settings
from maps_bridge.providers import MapsProvider


@lru_cache(maxsize=4)
def get_provider(provider_name: str | None = None) -> MapsProvider:
    """Return a MapsProvider (mock, serpapi, or google_places).

    When *provider_name* is omitted, falls back to ``settings.MAPS_PROVIDER``.
    """
    active = provider_name or settings.MAPS_PROVIDER
    if active == "mock":
        from maps_bridge.providers.mock import MockMapsProvider

        return MockMapsProvider()
    if settings.MAPS_PROVIDER == "serpapi":
        if not settings.SERPAPI_API_KEY:
            raise ValueError("SERPAPI_API_KEY must be set when MAPS_PROVIDER=serpapi")
        from maps_bridge.cache import CachingMapsProvider, SQLiteCache
        from maps_bridge.providers.serpapi import SerpAPIMapsProvider

        inner = SerpAPIMapsProvider(
            api_key=settings.SERPAPI_API_KEY, max_pages=settings.MAPS_MAX_PAGES
        )
        cache = SQLiteCache(db_path=settings.CACHE_DB_PATH, prefix="serpapi")
        return CachingMapsProvider(inner, cache)
    if active == "google_places":
        if not settings.GOOGLE_MAPS_API_KEY:
            raise ValueError("GOOGLE_MAPS_API_KEY must be set when MAPS_PROVIDER=google_places")
        from maps_bridge.cache import CachingMapsProvider, SQLiteCache
        from maps_bridge.providers.google_places import GooglePlacesProvider

        gp_inner = GooglePlacesProvider(
            api_key=settings.GOOGLE_MAPS_API_KEY, max_pages=settings.MAPS_MAX_PAGES
        )
        gp_cache = SQLiteCache(db_path=settings.CACHE_DB_PATH, prefix="google_places")
        return CachingMapsProvider(gp_inner, gp_cache)
    raise NotImplementedError(f"Unknown provider: {active!r}")
