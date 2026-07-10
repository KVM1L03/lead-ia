"""Provider singleton for maps_bridge — importable without starting the MCP server.

Importing this module does NOT start the FastMCP stdio loop. Safe to import from
ai_worker when MAPS_TRANSPORT=inline (provider runs in-process).
"""

from __future__ import annotations

from functools import lru_cache

from maps_bridge.config import settings
from maps_bridge.providers import MapsProvider


@lru_cache(maxsize=1)
def get_provider() -> MapsProvider:
    """Return the configured MapsProvider singleton (mock or serpapi)."""
    if settings.MAPS_PROVIDER == "mock":
        from maps_bridge.providers.mock import MockMapsProvider

        return MockMapsProvider()
    if settings.MAPS_PROVIDER == "serpapi":
        if not settings.SERPAPI_API_KEY:
            raise ValueError("SERPAPI_API_KEY must be set when MAPS_PROVIDER=serpapi")
        from maps_bridge.cache import CachingMapsProvider, SQLiteCache
        from maps_bridge.providers.serpapi import SerpAPIMapsProvider

        inner = SerpAPIMapsProvider(api_key=settings.SERPAPI_API_KEY)
        cache = SQLiteCache(db_path=settings.CACHE_DB_PATH, prefix="serpapi")
        return CachingMapsProvider(inner, cache)
    raise NotImplementedError(f"Unknown provider: {settings.MAPS_PROVIDER!r}")
