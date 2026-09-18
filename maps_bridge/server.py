"""maps_bridge MCP server — exposes search_places, get_place_details, fetch_site tools."""

from fastmcp import FastMCP

from maps_bridge.config import settings
from maps_bridge.provider_factory import get_provider
from maps_bridge.site_fetcher import fetch_site_live, fetch_site_mock
from shared.schemas import FetchedSite, PlaceDetails, PlaceSearchResult

mcp = FastMCP("maps-bridge")


@mcp.tool()
async def search_places(query: str, limit: int = 20) -> list[PlaceSearchResult]:
    provider = get_provider(settings.MAPS_PROVIDER)
    return await provider.search_places(query, limit)


@mcp.tool()
async def get_place_details(place_id: str) -> PlaceDetails:
    provider = get_provider(settings.MAPS_PROVIDER)
    return await provider.get_place_details(place_id)


@mcp.tool()
async def fetch_site(url: str) -> FetchedSite:
    if settings.MAPS_PROVIDER == "mock":
        return await fetch_site_mock(url)
    return await fetch_site_live(url)


if __name__ == "__main__":
    mcp.run(show_banner=False)
