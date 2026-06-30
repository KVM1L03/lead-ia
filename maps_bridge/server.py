"""maps_bridge MCP server — exposes search_places and get_place_details tools."""

from functools import lru_cache

from fastmcp import FastMCP

from maps_bridge.config import settings
from maps_bridge.providers import MapsProvider
from shared.schemas import PlaceDetails, PlaceSearchResult

mcp = FastMCP("maps-bridge")


@lru_cache(maxsize=1)
def _get_provider() -> MapsProvider:
    if settings.MAPS_PROVIDER == "mock":
        from maps_bridge.providers.mock import MockMapsProvider

        return MockMapsProvider()
    if settings.MAPS_PROVIDER == "serpapi":
        if not settings.SERPAPI_API_KEY:
            raise ValueError("SERPAPI_API_KEY must be set when MAPS_PROVIDER=serpapi")
        from maps_bridge.cache import CachingMapsProvider, SQLiteCache
        from maps_bridge.providers.serpapi import SerpAPIMapsProvider

        inner = SerpAPIMapsProvider(api_key=settings.SERPAPI_API_KEY)
        cache = SQLiteCache(db_path=settings.CACHE_DB_PATH)
        return CachingMapsProvider(inner, cache)
    raise NotImplementedError(f"Unknown provider: '{settings.MAPS_PROVIDER}'")


@mcp.tool()
async def search_places(query: str, limit: int = 20) -> list[PlaceSearchResult]:
    provider = _get_provider()
    return await provider.search_places(query, limit)


@mcp.tool()
async def get_place_details(place_id: str) -> PlaceDetails:
    provider = _get_provider()
    return await provider.get_place_details(place_id)


if __name__ == "__main__":
    mcp.run()
