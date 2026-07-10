import pytest

from maps_bridge.provider_factory import get_provider
from maps_bridge.server import get_place_details, mcp, search_places


def test_server_imports() -> None:
    assert mcp is not None


async def test_tools_registered() -> None:
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert "search_places" in names
    assert "get_place_details" in names


async def test_search_places_returns_mock_results() -> None:
    results = await search_places(query="dental clinics Wrocław", limit=3)
    assert 0 < len(results) <= 3


async def test_get_place_details_returns_known_fixture() -> None:
    # Uses a recorded Google Places id (from dental_clinics_wroc_aw fixtures)
    details = await get_place_details(place_id="ChIJIzcRfHDqD0cRZ9YugAK02ZE")
    assert details.name == "Dental Center DentalCover"


def test_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    get_provider.cache_clear()
    monkeypatch.setattr("maps_bridge.config.settings.MAPS_PROVIDER", "unknown_xyz")
    try:
        with pytest.raises(NotImplementedError, match="Unknown provider"):
            get_provider()
    finally:
        get_provider.cache_clear()
