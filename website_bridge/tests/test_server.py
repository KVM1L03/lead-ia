import pytest

from website_bridge.provider_factory import get_provider
from website_bridge.server import fetch_website_facts, mcp


def test_server_imports() -> None:
    assert mcp is not None


async def test_tool_registered() -> None:
    tools = await mcp.list_tools()
    assert "fetch_website_facts" in {t.name for t in tools}


async def test_fetch_returns_facts_under_mock() -> None:
    facts = await fetch_website_facts(url="https://dentysta-booking.example")
    assert "booksy" in facts.booking_keywords_found


def test_unknown_provider_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    get_provider.cache_clear()
    monkeypatch.setattr("website_bridge.config.settings.WEBSITE_PROVIDER", "nope_xyz")
    try:
        with pytest.raises(NotImplementedError, match="Unknown provider"):
            get_provider()
    finally:
        get_provider.cache_clear()
