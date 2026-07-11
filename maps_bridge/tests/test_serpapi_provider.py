"""Tests for SerpAPIMapsProvider and CachingMapsProvider.

Cassettes in tests/cassettes/ replay SerpAPI responses without network calls.
Cassettes were authored from real SerpAPI response shapes; to re-record with a
live key run the provider manually and update the JSON files.
"""

import json
import logging
from pathlib import Path

import httpx
import pytest

from maps_bridge.cache import CachingMapsProvider, SQLiteCache
from maps_bridge.errors import RateLimitError
from maps_bridge.providers.serpapi import SerpAPIMapsProvider

CASSETTES_DIR = Path(__file__).parent / "cassettes"


class _CassetteTransport(httpx.AsyncBaseTransport):
    """Replays a pre-recorded cassette; counts HTTP calls to detect cache hits."""

    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.call_count = 0
        self._content = content
        self._status_code = status_code

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.call_count += 1
        return httpx.Response(
            status_code=self._status_code,
            content=self._content,
            headers={"content-type": "application/json"},
        )


def _cassette(name: str, *, status_code: int | None = None) -> _CassetteTransport:
    raw = json.loads((CASSETTES_DIR / name).read_text())
    code: int = status_code if status_code is not None else raw["status_code"]
    body: bytes = json.dumps(raw["body"]).encode()
    return _CassetteTransport(content=body, status_code=code)


def _page(name: str) -> tuple[int, bytes]:
    """Load a cassette file as a (status_code, body_bytes) tuple for sequential replay."""
    raw = json.loads((CASSETTES_DIR / name).read_text())
    status_code: int = raw["status_code"]
    body: bytes = json.dumps(raw["body"]).encode()
    return status_code, body


class _SequentialCassetteTransport(httpx.AsyncBaseTransport):
    """Replays canned (status_code, body) responses in order; repeats the last
    one if called more times than there are responses. Records each request's
    `start` query param for pagination-offset assertions."""

    def __init__(self, responses: list[tuple[int, bytes]]) -> None:
        self.call_count = 0
        self.starts: list[str | None] = []
        self._responses = responses

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.starts.append(request.url.params.get("start"))
        index = min(self.call_count, len(self._responses) - 1)
        status_code, content = self._responses[index]
        self.call_count += 1
        return httpx.Response(
            status_code=status_code,
            content=content,
            headers={"content-type": "application/json"},
        )


def _provider(
    transport: httpx.AsyncBaseTransport,
    *,
    max_pages: int = 5,
    page_size: int = 20,
) -> SerpAPIMapsProvider:
    client = httpx.AsyncClient(transport=transport)
    return SerpAPIMapsProvider(
        api_key="test_key", client=client, max_pages=max_pages, page_size=page_size
    )


# ---------------------------------------------------------------------------
# SerpAPIMapsProvider — search
# ---------------------------------------------------------------------------


async def test_search_returns_expected_shape() -> None:
    transport = _cassette("search_dentist_warsaw.json")
    provider = _provider(transport)
    results = await provider.search_places("dentist warsaw", 5)
    assert 0 < len(results) <= 5
    for r in results:
        assert r.id
        assert r.name
        assert isinstance(r.lat, float)
        assert isinstance(r.rating, float)
        assert isinstance(r.review_count, int)


async def test_search_respects_limit() -> None:
    transport = _cassette("search_dentist_warsaw.json")
    provider = _provider(transport)
    results = await provider.search_places("dentist warsaw", 2)
    assert len(results) <= 2


async def test_search_maps_fields_correctly() -> None:
    transport = _cassette("search_dentist_warsaw.json")
    provider = _provider(transport)
    results = await provider.search_places("dentist warsaw", 5)
    first = results[0]
    assert first.id == "ChIJtest001"
    assert first.name == "Medident Dental Clinic"
    assert first.category == "Dentist"
    assert first.rating == 4.8
    assert first.review_count == 245
    assert abs(first.lat - 52.2297) < 0.001


# ---------------------------------------------------------------------------
# SerpAPIMapsProvider — place details
# ---------------------------------------------------------------------------


async def test_get_place_details_shape() -> None:
    transport = _cassette("get_place_details.json")
    provider = _provider(transport)
    details = await provider.get_place_details("ChIJtest001")
    assert details.name == "Medident Dental Clinic"
    assert details.website == "https://medident.pl"
    assert details.phone == "+48 22 826 1234"
    assert len(details.hours) == 5
    assert details.hours[0].startswith("Monday:")


async def test_get_place_details_parses_list_type_and_hours() -> None:
    transport = _cassette("get_place_details_list_shape.json")
    provider = _provider(transport)
    details = await provider.get_place_details("ChIJlive001")
    assert details.category == "Dentist, Cosmetic dentist, Periodontist"
    assert details.hours == ["tuesday: 9 AM-9 PM", "monday: 9 AM-9 PM"]


async def test_get_place_details_uses_place_id_param() -> None:
    transport = _cassette("get_place_details.json")

    class _CapturingTransport(httpx.AsyncBaseTransport):
        def __init__(self, inner: _CassetteTransport) -> None:
            self.inner = inner
            self.last_url: str = ""

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.last_url = str(request.url)
            return await self.inner.handle_async_request(request)

    capture = _CapturingTransport(transport)
    client = httpx.AsyncClient(transport=capture)
    capturing_provider = SerpAPIMapsProvider(api_key="test_key", client=client)

    await capturing_provider.get_place_details("ChIJtest001")
    assert "place_id=ChIJtest001" in capture.last_url
    assert "data_id=" not in capture.last_url


async def test_get_place_details_data_id_requires_coords() -> None:
    transport = _cassette("get_place_details.json")
    provider = _provider(transport)
    with pytest.raises(ValueError, match="lat and lng"):
        await provider.get_place_details("0x471ecce11f7d7f:0xabc001")


async def test_get_place_details_data_id_with_coords() -> None:
    transport = _cassette("get_place_details.json")

    class _CapturingTransport(httpx.AsyncBaseTransport):
        def __init__(self, inner: _CassetteTransport) -> None:
            self.inner = inner
            self.last_url: str = ""

        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            self.last_url = str(request.url)
            return await self.inner.handle_async_request(request)

    capture = _CapturingTransport(transport)
    client = httpx.AsyncClient(transport=capture)
    provider = SerpAPIMapsProvider(api_key="test_key", client=client)

    await provider.get_place_details("0x471ecce11f7d7f:0xabc001", lat=52.2297, lng=21.0122)
    assert "type=place" in capture.last_url
    assert "data=%214m5%213m4%211s0x471ecce11f7d7f%3A0xabc001" in capture.last_url
    assert "place_id=" not in capture.last_url


# ---------------------------------------------------------------------------
# SerpAPIMapsProvider — error handling
# ---------------------------------------------------------------------------


async def test_rate_limit_raises_rate_limit_error() -> None:
    transport = _cassette("rate_limit_429.json")
    provider = _provider(transport)
    with pytest.raises(RateLimitError):
        await provider.search_places("dentist warsaw", 5)


async def test_rate_limit_is_not_retried() -> None:
    transport = _cassette("rate_limit_429.json")
    provider = _provider(transport)
    with pytest.raises(RateLimitError):
        await provider.search_places("dentist warsaw", 5)
    # tenacity must not retry on RateLimitError — only one HTTP call
    assert transport.call_count == 1


# ---------------------------------------------------------------------------
# CachingMapsProvider — cache behaviour
# ---------------------------------------------------------------------------


async def test_cache_hit_skips_http(tmp_path: Path) -> None:
    transport = _cassette("search_dentist_warsaw.json")
    inner = _provider(transport)
    cache = SQLiteCache(str(tmp_path / "cache.db"))
    provider = CachingMapsProvider(inner, cache)

    results1 = await provider.search_places("dentist warsaw", 5)
    assert transport.call_count == 1

    results2 = await provider.search_places("dentist warsaw", 5)
    # cache served the second call — no new HTTP request
    assert transport.call_count == 1
    assert len(results1) == len(results2)
    assert results1[0].id == results2[0].id


async def test_cache_miss_calls_http(tmp_path: Path) -> None:
    transport = _cassette("search_dentist_warsaw.json")
    inner = _provider(transport)
    cache = SQLiteCache(str(tmp_path / "cache.db"))
    provider = CachingMapsProvider(inner, cache)

    await provider.search_places("dentist warsaw", 5)
    await provider.search_places("coffee berlin", 5)  # different query → cache miss
    assert transport.call_count == 2


async def test_cache_details_hit_skips_http(tmp_path: Path) -> None:
    transport = _cassette("get_place_details.json")
    inner = _provider(transport)
    cache = SQLiteCache(str(tmp_path / "cache.db"))
    provider = CachingMapsProvider(inner, cache)

    d1 = await provider.get_place_details("ChIJtest001")
    d2 = await provider.get_place_details("ChIJtest001")
    assert transport.call_count == 1
    assert d1.name == d2.name


# ---------------------------------------------------------------------------
# SQLiteCache — TTL
# ---------------------------------------------------------------------------


def test_cache_evict_expired_removes_stale_entry(tmp_path: Path) -> None:
    cache = SQLiteCache(str(tmp_path / "cache.db"), ttl=0)
    cache.set_search("q", 5, '["stub"]')
    cache.evict_expired()
    assert cache.get_search("q", 5) is None


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


async def test_search_paginates_to_reach_limit() -> None:
    transport = _SequentialCassetteTransport(
        [
            _page("serp_search_page1_full.json"),
            _page("serp_search_page2_full.json"),
            _page("serp_search_page3_partial.json"),
        ]
    )
    provider = _provider(transport, page_size=3)
    results = await provider.search_places("dentist warsaw", 8)
    assert transport.call_count == 3
    assert len(results) == 8


async def test_search_one_page_when_limit_fits() -> None:
    transport = _SequentialCassetteTransport([_page("serp_search_page1_full.json")])
    provider = _provider(transport, page_size=3)
    results = await provider.search_places("dentist warsaw", 3)
    assert transport.call_count == 1
    assert len(results) == 3


async def test_search_truncates_to_limit_exactly() -> None:
    transport = _SequentialCassetteTransport(
        [
            _page("serp_search_page1_full.json"),
            _page("serp_search_page2_full.json"),
            _page("serp_search_page3_partial.json"),
        ]
    )
    provider = _provider(transport, page_size=3)
    results = await provider.search_places("dentist warsaw", 7)
    assert transport.call_count == 3
    assert len(results) == 7  # 8 collected across 3 pages, truncated to 7 — never 8


async def test_search_stops_when_page_not_full() -> None:
    """A page returning fewer than page_size results signals exhaustion — stop early."""
    transport = _SequentialCassetteTransport(
        [
            _page("serp_search_page1_full.json"),
            _page("serp_search_page3_partial.json"),  # only 2 results — last page
        ]
    )
    provider = _provider(transport, page_size=3)
    results = await provider.search_places("dentist warsaw", 100)
    assert transport.call_count == 2  # stops early — doesn't chase a 3rd page that won't exist
    assert len(results) == 5


async def test_search_max_pages_guard_stops_pagination() -> None:
    transport = _SequentialCassetteTransport([_page("serp_search_page1_full.json")])
    provider = _provider(transport, max_pages=3, page_size=3)
    results = await provider.search_places("dentist warsaw", 1000)
    assert transport.call_count == 3
    assert len(results) == 9  # 3 pages * 3 results/page — nowhere near the requested 1000


async def test_search_uses_start_offset_for_pagination() -> None:
    transport = _SequentialCassetteTransport(
        [
            _page("serp_search_page1_full.json"),
            _page("serp_search_page2_full.json"),
            _page("serp_search_page3_partial.json"),
        ]
    )
    provider = _provider(transport, page_size=3)
    await provider.search_places("dentist warsaw", 8)
    assert transport.starts == ["0", "3", "6"]


async def test_search_logs_pages_and_results(caplog: pytest.LogCaptureFixture) -> None:
    transport = _SequentialCassetteTransport(
        [
            _page("serp_search_page1_full.json"),
            _page("serp_search_page2_full.json"),
            _page("serp_search_page3_partial.json"),
        ]
    )
    provider = _provider(transport, page_size=3)
    with caplog.at_level(logging.INFO, logger="maps_bridge.providers.serpapi"):
        await provider.search_places("dentist warsaw", 8)
    assert any(
        "pages=3" in record.message and "results=8" in record.message for record in caplog.records
    )


async def test_cache_does_not_collide_across_limits(tmp_path: Path) -> None:
    """A limit=2 cache entry must never be served for a limit=3 (or vice versa) request."""
    transport = _cassette("search_dentist_warsaw.json")  # 3 results — always a "partial" page
    inner = _provider(transport)
    cache = SQLiteCache(str(tmp_path / "cache.db"), prefix="serpapi")
    provider = CachingMapsProvider(inner, cache)

    small = await provider.search_places("dentist warsaw", 2)
    assert transport.call_count == 1
    assert len(small) == 2

    big = await provider.search_places("dentist warsaw", 3)
    assert transport.call_count == 2  # different limit → cache miss → a fresh HTTP call
    assert len(big) == 3
