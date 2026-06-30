import pytest

from maps_bridge.server import get_place_details, mcp, search_places


def test_server_imports() -> None:
    assert mcp is not None


async def test_tools_registered() -> None:
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert "search_places" in names
    assert "get_place_details" in names


async def test_search_places_raises_without_provider() -> None:
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        await search_places(query="coffee shops in NYC", limit=5)


async def test_get_place_details_raises_without_provider() -> None:
    with pytest.raises(NotImplementedError, match="not yet implemented"):
        await get_place_details(place_id="ChIJabc123")
