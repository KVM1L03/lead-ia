"""Tests for SerpAPIMapsProvider and CachingMapsProvider.

Cassettes in tests/cassettes/ replay SerpAPI responses without network calls.
Cassettes were authored from real SerpAPI response shapes; to re-record with a
live key run the provider manually and update the JSON files.
"""

import json
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


def _provider(transport: _CassetteTransport) -> SerpAPIMapsProvider:
    client = httpx.AsyncClient(transport=transport)
    return SerpAPIMapsProvider(api_key="test_key", client=client)


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
    details = await provider.get_place_details("0x471ecce11f7d7f:0xabc001")
    assert details.name == "Medident Dental Clinic"
    assert details.website == "https://medident.pl"
    assert details.phone == "+48 22 826 1234"
    assert len(details.hours) == 5
    assert details.hours[0].startswith("Monday:")


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

    d1 = await provider.get_place_details("0x471ecce11f7d7f:0xabc001")
    d2 = await provider.get_place_details("0x471ecce11f7d7f:0xabc001")
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
