"""maps_bridge MCP server — exposes search_places and get_place_details tools."""

from fastmcp import FastMCP

from maps_bridge.provider_factory import get_provider
from shared.schemas import PlaceDetails, PlaceSearchResult

mcp = FastMCP("maps-bridge")


@mcp.tool()
async def search_places(query: str, limit: int = 20) -> list[PlaceSearchResult]:
    provider = get_provider()
    return await provider.search_places(query, limit)


@mcp.tool()
async def get_place_details(place_id: str) -> PlaceDetails:
    provider = get_provider()
    return await provider.get_place_details(place_id)


if __name__ == "__main__":
    mcp.run(show_banner=False)
