"""Tests for GooglePlacesProvider and its integration with CachingMapsProvider.

All tests use hand-crafted cassette fixtures — no live HTTP, no real API key.
The cassettes contain no credentials (the provider sends the key in a request
header that is not persisted to cassette files).
"""

import json
import logging
from pathlib import Path

import httpx
import pytest

from maps_bridge.cache import CachingMapsProvider, SQLiteCache
from maps_bridge.errors import RateLimitError
from maps_bridge.providers.google_places import (
    _DETAILS_MASK,
    _SEARCH_MASK,
    GooglePlacesProvider,
)

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


class _CapturingTransport(httpx.AsyncBaseTransport):
    """Wraps a cassette transport and records the last request for header inspection."""

    def __init__(self, inner: _CassetteTransport) -> None:
        self.inner = inner
        self.last_request: httpx.Request | None = None

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.last_request = request
        return await self.inner.handle_async_request(request)


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
    JSON body for assertions about what was actually sent (e.g. maxResultCount)."""

    def __init__(self, responses: list[tuple[int, bytes]]) -> None:
        self.call_count = 0
        self.request_bodies: list[dict[str, object]] = []
        self._responses = responses

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if request.content:
            self.request_bodies.append(json.loads(request.content))
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
    page_token_delay: float = 0.0,
) -> GooglePlacesProvider:
    client = httpx.AsyncClient(transport=transport)
    return GooglePlacesProvider(
        api_key="test_key",
        client=client,
        max_pages=max_pages,
        page_token_delay=page_token_delay,
    )


# ---------------------------------------------------------------------------
# FieldMask invariants — cost control (sync, no network)
# ---------------------------------------------------------------------------


def test_search_mask_excludes_rating_and_reviews() -> None:
    """COST INVARIANT: these fields upgrade every Text Search call to Enterprise tier.

    The free quota drops from 5 000 to 1 000 calls/month with no warning.
    If this test fails, a FieldMask change reintroduced a cost-escalating field.
    """
    forbidden = {"rating", "userRatingCount", "reviews", "userRatings"}
    mask_fields = {f.replace("places.", "") for f in _SEARCH_MASK.split(",")}
    overlap = mask_fields & forbidden
    assert not overlap, (
        f"Search FieldMask contains Enterprise-tier fields: {overlap}. "
        "Remove them to stay at Pro tier (5 000 free calls/month)."
    )


def test_details_mask_excludes_rating_and_reviews() -> None:
    """Details FieldMask must not include rating/reviews (schema invariant T-GP.1)."""
    forbidden = {"rating", "userRatingCount", "reviews", "userRatings", "editorialSummary"}
    mask_fields = set(_DETAILS_MASK.split(","))
    overlap = mask_fields & forbidden
    assert not overlap, f"Details FieldMask contains excluded fields: {overlap}."


# ---------------------------------------------------------------------------
# GooglePlacesProvider — search
# ---------------------------------------------------------------------------


async def test_search_returns_expected_shape() -> None:
    transport = _cassette("gp_search_dentist_warsaw.json")
    provider = _provider(transport)
    results = await provider.search_places("dentist warsaw", 5)
    assert 0 < len(results) <= 5
    for r in results:
        assert r.id
        assert r.name
        assert isinstance(r.lat, float)
        assert r.rating is None
        assert r.review_count is None


async def test_search_field_mask_sent_as_header() -> None:
    """FieldMask goes in the X-Goog-FieldMask header, not a query param."""
    inner = _cassette("gp_search_dentist_warsaw.json")
    capture = _CapturingTransport(inner)
    provider = _provider(capture)

    await provider.search_places("dentist warsaw", 5)

    assert capture.last_request is not None
    assert "x-goog-fieldmask" in capture.last_request.headers
    mask = capture.last_request.headers["x-goog-fieldmask"]
    assert "rating" not in mask
    assert "userRatingCount" not in mask
    assert "reviews" not in mask


async def test_search_respects_limit() -> None:
    transport = _cassette("gp_search_dentist_warsaw.json")
    provider = _provider(transport)
    results = await provider.search_places("dentist warsaw", 2)
    assert len(results) <= 2


async def test_search_maps_category_from_primary_type() -> None:
    transport = _cassette("gp_search_dentist_warsaw.json")
    provider = _provider(transport)
    results = await provider.search_places("dentist warsaw", 5)
    first = results[0]
    assert first.id == "ChIJgp001"
    assert first.name == "Medident Dental Clinic"
    assert first.category == "Dentist"  # primaryType "dentist" → title-cased
    assert first.rating is None
    assert first.review_count is None
    assert abs(first.lat - 52.2297) < 0.001


# ---------------------------------------------------------------------------
# GooglePlacesProvider — place details
# ---------------------------------------------------------------------------


async def test_get_place_details_shape() -> None:
    transport = _cassette("gp_details_ChIJgp001.json")
    provider = _provider(transport)
    details = await provider.get_place_details("ChIJgp001")
    assert details.id == "ChIJgp001"
    assert details.name == "Medident Dental Clinic"
    assert details.website == "https://medident.pl"
    assert details.phone == "+48 22 826 1234"
    assert len(details.hours) == 5
    assert details.hours[0].startswith("Monday:")


async def test_get_place_details_rating_is_none() -> None:
    transport = _cassette("gp_details_ChIJgp001.json")
    provider = _provider(transport)
    details = await provider.get_place_details("ChIJgp001")
    assert details.rating is None
    assert details.review_count is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


async def test_rate_limit_raises_rate_limit_error() -> None:
    transport = _cassette("gp_rate_limit_429.json")
    provider = _provider(transport)
    with pytest.raises(RateLimitError):
        await provider.search_places("dentist warsaw", 5)


async def test_rate_limit_is_not_retried() -> None:
    transport = _cassette("gp_rate_limit_429.json")
    provider = _provider(transport)
    with pytest.raises(RateLimitError):
        await provider.search_places("dentist warsaw", 5)
    assert transport.call_count == 1


# ---------------------------------------------------------------------------
# CachingMapsProvider — cache behaviour
# ---------------------------------------------------------------------------


async def test_cache_hit_skips_http(tmp_path: Path) -> None:
    transport = _cassette("gp_search_dentist_warsaw.json")
    inner = _provider(transport)
    cache = SQLiteCache(str(tmp_path / "cache.db"), prefix="google_places")
    provider = CachingMapsProvider(inner, cache)

    results1 = await provider.search_places("dentist warsaw", 5)
    assert transport.call_count == 1

    results2 = await provider.search_places("dentist warsaw", 5)
    assert transport.call_count == 1  # served from cache
    assert len(results1) == len(results2)
    assert results1[0].id == results2[0].id


async def test_cache_keys_are_provider_scoped(tmp_path: Path) -> None:
    """Google Places and SerpAPI must not share cache entries for the same query."""
    shared_db = str(tmp_path / "shared.db")

    # Pre-populate a serpapi cache entry for the same query
    serpapi_cache = SQLiteCache(db_path=shared_db, prefix="serpapi")
    serpapi_cache.set_search(
        "dentist warsaw",
        5,
        '[{"id":"serpapi-place","name":"SerpAPI Place","address":"1 Road",'
        '"lat":0.0,"lng":0.0,"category":"Dentist","rating":4.8,"review_count":245}]',
    )

    # Google Places provider with the same db but different prefix
    gp_transport = _cassette("gp_search_dentist_warsaw.json")
    gp_inner = _provider(gp_transport)
    gp_cache = SQLiteCache(db_path=shared_db, prefix="google_places")
    gp_provider = CachingMapsProvider(gp_inner, gp_cache)

    results = await gp_provider.search_places("dentist warsaw", 5)

    # Must have made an HTTP call (cache miss — different prefix)
    assert gp_transport.call_count == 1
    # Must return Google Places data (rating=None), not the stale SerpAPI data
    assert results[0].rating is None
    assert results[0].id != "serpapi-place"


async def test_details_cache_hit_skips_http(tmp_path: Path) -> None:
    transport = _cassette("gp_details_ChIJgp001.json")
    inner = _provider(transport)
    cache = SQLiteCache(str(tmp_path / "cache.db"), prefix="google_places")
    provider = CachingMapsProvider(inner, cache)

    d1 = await provider.get_place_details("ChIJgp001")
    d2 = await provider.get_place_details("ChIJgp001")
    assert transport.call_count == 1
    assert d1.name == d2.name


# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


async def test_search_paginates_to_reach_limit() -> None:
    transport = _SequentialCassetteTransport(
        [
            _page("gp_search_page1_of_3.json"),
            _page("gp_search_page2_of_3.json"),
            _page("gp_search_page3_of_3.json"),
        ]
    )
    provider = _provider(transport)
    results = await provider.search_places("dentist warsaw", 8)
    assert transport.call_count == 3
    assert len(results) == 8
    assert results[0].id == "ChIJpg101"
    assert results[-1].id == "ChIJpg302"


async def test_search_one_page_when_limit_fits() -> None:
    transport = _SequentialCassetteTransport([_page("gp_search_page1_of_3.json")])
    provider = _provider(transport)
    results = await provider.search_places("dentist warsaw", 3)
    # page1 has a nextPageToken, but the limit is already satisfied — must not fetch page 2
    assert transport.call_count == 1
    assert len(results) == 3


async def test_search_truncates_to_limit_exactly() -> None:
    transport = _SequentialCassetteTransport(
        [
            _page("gp_search_page1_of_3.json"),
            _page("gp_search_page2_of_3.json"),
            _page("gp_search_page3_of_3.json"),
        ]
    )
    provider = _provider(transport)
    results = await provider.search_places("dentist warsaw", 7)
    assert transport.call_count == 3  # 3+3=6 < 7, needs the 3rd page
    assert len(results) == 7  # 8 collected across 3 pages, truncated to 7 — never 8


async def test_search_max_pages_guard_stops_pagination() -> None:
    transport = _SequentialCassetteTransport([_page("gp_search_always_full_page.json")])
    provider = _provider(transport, max_pages=3)
    results = await provider.search_places("dentist warsaw", 1000)
    assert transport.call_count == 3  # guard stops it even though nextPageToken never runs out
    assert len(results) == 15  # 3 pages * 5 places/page — nowhere near the requested 1000


async def test_page_token_not_ready_retries_with_backoff() -> None:
    transport = _SequentialCassetteTransport(
        [
            _page("gp_search_page1_of_3.json"),  # page 1 succeeds, returns a token
            _page(
                "gp_page_token_not_ready_400.json"
            ),  # first attempt to use the token: not ready yet
            _page("gp_search_page3_of_3.json"),  # retry succeeds
        ]
    )
    provider = _provider(transport)
    results = await provider.search_places("dentist warsaw", 5)
    assert transport.call_count == 3
    assert len(results) == 5  # 3 (page1) + 2 (page3, after the retried page2 attempt)


async def test_search_never_requests_more_than_remaining_count() -> None:
    """COST INVARIANT: maxResultCount must equal exactly what's still needed — never over-request."""
    transport = _SequentialCassetteTransport(
        [
            _page("gp_search_page1_of_3.json"),
            _page("gp_search_page3_of_3.json"),
        ]
    )
    provider = _provider(transport)
    await provider.search_places("dentist warsaw", 7)
    assert transport.request_bodies[0]["maxResultCount"] == 7  # min(7 - 0, 20)
    assert transport.request_bodies[1]["maxResultCount"] == 4  # min(7 - 3, 20)


async def test_search_logs_pages_and_results(caplog: pytest.LogCaptureFixture) -> None:
    transport = _SequentialCassetteTransport(
        [
            _page("gp_search_page1_of_3.json"),
            _page("gp_search_page2_of_3.json"),
            _page("gp_search_page3_of_3.json"),
        ]
    )
    provider = _provider(transport)
    with caplog.at_level(logging.INFO, logger="maps_bridge.providers.google_places"):
        await provider.search_places("dentist warsaw", 8)
    assert any(
        "pages=3" in record.message and "results=8" in record.message for record in caplog.records
    )


async def test_cache_does_not_collide_across_limits(tmp_path: Path) -> None:
    """A limit=20 cache entry must never be served for a limit=3 (or vice versa) request."""
    transport = _cassette("gp_search_dentist_warsaw.json")  # single-page, no nextPageToken
    inner = _provider(transport)
    cache = SQLiteCache(str(tmp_path / "cache.db"), prefix="google_places")
    provider = CachingMapsProvider(inner, cache)

    small = await provider.search_places("dentist warsaw", 2)
    assert transport.call_count == 1
    assert len(small) == 2

    big = await provider.search_places("dentist warsaw", 3)
    assert transport.call_count == 2  # different limit → cache miss → a fresh HTTP call
    assert len(big) == 3
