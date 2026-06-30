"""maps_bridge MCP server — exposes search_places and get_place_details tools."""

from fastmcp import FastMCP

from maps_bridge.config import settings
from maps_bridge.providers import MapsProvider
from shared.schemas import PlaceDetails, PlaceSearchResult

mcp = FastMCP("maps-bridge")


def _get_provider() -> MapsProvider:
    raise NotImplementedError(
        f"Provider '{settings.MAPS_PROVIDER}' not yet implemented. "
        "Add maps_bridge/providers/mock.py (T1.2) or providers/serpapi.py (T1.3)."
    )


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
