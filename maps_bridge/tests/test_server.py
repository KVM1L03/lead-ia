import pytest

from maps_bridge.server import _get_provider, get_place_details, mcp, search_places


def test_server_imports() -> None:
    assert mcp is not None


async def test_tools_registered() -> None:
    tools = await mcp.list_tools()
    names = {t.name for t in tools}
    assert "search_places" in names
    assert "get_place_details" in names


async def test_search_places_returns_mock_results() -> None:
    results = await search_places(query="dental", limit=3)
    assert 0 < len(results) <= 3
    assert all("dental" in r.category.lower() or "dental" in r.name.lower() for r in results)


async def test_get_place_details_returns_known_fixture() -> None:
    details = await get_place_details(place_id="dental-warsaw-001")
    assert details.name == "Klinika Stomatologiczna Centrum"


def test_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _get_provider.cache_clear()
    monkeypatch.setattr("maps_bridge.config.settings.MAPS_PROVIDER", "unknown_xyz")
    try:
        with pytest.raises(NotImplementedError, match="Unknown provider"):
            _get_provider()
    finally:
        _get_provider.cache_clear()
