from website_bridge.providers.mock import MockWebsiteProvider


async def test_booking_sentinel_returns_booking_facts() -> None:
    provider = MockWebsiteProvider()
    facts = await provider.fetch_website_facts("https://dentysta-booking.example")
    assert "booksy" in facts.booking_keywords_found
    assert facts.copyright_year == 2026


async def test_outdated_sentinel_has_no_ssl() -> None:
    provider = MockWebsiteProvider()
    facts = await provider.fetch_website_facts("http://dentysta-2012.example")
    assert facts.has_ssl is False
    assert facts.generator_meta == "WordPress 3.2"


async def test_unknown_url_falls_back_deterministically() -> None:
    provider = MockWebsiteProvider()
    facts = await provider.fetch_website_facts("https://something-unknown.example")
    assert facts.booking_keywords_found == []
    assert facts.has_ssl is True
