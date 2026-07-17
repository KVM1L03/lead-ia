from shared.schemas import WebsiteFacts
from website_bridge.cache import CachingWebsiteProvider, InMemoryCache


def _facts(year: int) -> WebsiteFacts:
    return WebsiteFacts(
        has_ssl=True,
        has_viewport_meta=True,
        generator_meta=None,
        page_size_kb=1.0,
        has_contact_form=False,
        booking_keywords_found=[],
        has_phone_in_markup=False,
        social_links=[],
        has_schema_org=False,
        copyright_year=year,
        visible_text_excerpt="",
    )


class _CountingProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch_website_facts(self, url: str) -> WebsiteFacts:
        self.calls += 1
        return _facts(2000 + self.calls)


async def test_same_domain_hits_cache() -> None:
    inner = _CountingProvider()
    provider = CachingWebsiteProvider(inner, InMemoryCache())
    a = await provider.fetch_website_facts("https://clinic.example/home")
    b = await provider.fetch_website_facts("https://www.clinic.example/contact")
    assert inner.calls == 1
    assert a.copyright_year == b.copyright_year


async def test_different_domains_miss() -> None:
    inner = _CountingProvider()
    provider = CachingWebsiteProvider(inner, InMemoryCache())
    await provider.fetch_website_facts("https://a.example/")
    await provider.fetch_website_facts("https://b.example/")
    assert inner.calls == 2


def test_ttl_expiry_evicts(monkeypatch: object) -> None:
    import website_bridge.cache as cache_mod

    cache = InMemoryCache(ttl=10)
    times = iter([100.0, 130.0])
    monkeypatch.setattr(cache_mod.time, "time", lambda: next(times))  # type: ignore[attr-defined]
    cache.set("clinic.example", _facts(2020))
    assert cache.get("clinic.example") is None
