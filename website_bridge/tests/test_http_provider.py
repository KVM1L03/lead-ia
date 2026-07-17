import httpx
import pytest

import website_bridge.providers.http as http_mod
from website_bridge.errors import RobotsDisallowedError, WebsiteFetchError
from website_bridge.providers.http import HttpWebsiteProvider

_HTML = (
    b"<html><head><meta name='viewport' content='width=device-width'></head>"
    b"<body><a href='https://facebook.com/x'>fb</a>"
    b"<footer>Copyright 2024</footer></body></html>"
)


def _allow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_mod, "robots_allows", lambda url, ua: True)


async def test_happy_fetch_extracts_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow(monkeypatch)
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=_HTML))
    provider = HttpWebsiteProvider(user_agent="TestBot/1.0", transport=transport)
    facts = await provider.fetch_website_facts("https://clinic.example/")
    assert facts.has_ssl is True
    assert facts.has_viewport_meta is True
    assert facts.copyright_year == 2024
    assert len(facts.social_links) == 1


async def test_robots_disallow_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(http_mod, "robots_allows", lambda url, ua: False)
    provider = HttpWebsiteProvider(user_agent="TestBot/1.0")
    with pytest.raises(RobotsDisallowedError):
        await provider.fetch_website_facts("https://clinic.example/")


async def test_oversize_body_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow(monkeypatch)
    big = b"x" * 5000
    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=big))
    provider = HttpWebsiteProvider(user_agent="TestBot/1.0", max_bytes=1000, transport=transport)
    with pytest.raises(WebsiteFetchError):
        await provider.fetch_website_facts("https://clinic.example/")


async def test_http_error_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _allow(monkeypatch)
    transport = httpx.MockTransport(lambda req: httpx.Response(500))
    provider = HttpWebsiteProvider(user_agent="TestBot/1.0", transport=transport)
    with pytest.raises(WebsiteFetchError):
        await provider.fetch_website_facts("https://clinic.example/")
