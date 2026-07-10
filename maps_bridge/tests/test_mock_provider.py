"""Tests for MockMapsProvider backed by recorded Google Places fixtures."""

from __future__ import annotations

import pytest

from maps_bridge.providers.mock import MockMapsProvider, _load_fixtures


@pytest.fixture
def provider() -> MockMapsProvider:
    return MockMapsProvider()


# ---------------------------------------------------------------------------
# Fixture loading
# ---------------------------------------------------------------------------


def test_fixtures_load_without_error() -> None:
    _search_index, details_index, slugs, _slug_to_query = _load_fixtures()
    assert len(slugs) == 6
    assert len(details_index) == 30  # 6 queries x 5 details each


def test_all_loaded_results_have_none_rating() -> None:
    search_index, _, _, _ = _load_fixtures()
    for results in search_index.values():
        for r in results:
            assert r.rating is None
            assert r.review_count is None


# ---------------------------------------------------------------------------
# Exact / near match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_recorded_query_returns_its_results(provider: MockMapsProvider) -> None:
    results = await provider.search_places("dental clinics Wrocław", 10)
    assert len(results) == 5
    assert all(r.rating is None for r in results)


@pytest.mark.asyncio
async def test_exact_match_respects_limit(provider: MockMapsProvider) -> None:
    results = await provider.search_places("dental clinics Wrocław", 2)
    assert len(results) == 2


@pytest.mark.asyncio
async def test_subset_tokens_match_exact(provider: MockMapsProvider) -> None:
    # "dental wroclaw" tokens are a subset of "dental clinics Wrocław" tokens
    results = await provider.search_places("dental wroclaw", 10)
    assert len(results) == 5


# ---------------------------------------------------------------------------
# Fuzzy match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fuzzy_query_returns_related_results(provider: MockMapsProvider) -> None:
    results = await provider.search_places("dentist wrocław", 10)
    assert len(results) > 0


@pytest.mark.asyncio
async def test_city_token_guides_fuzzy_match(provider: MockMapsProvider) -> None:
    # "lawyers warszawa" → should match "law firms Warszawa" (not Wrocław)
    results = await provider.search_places("lawyers warszawa", 10)
    assert len(results) > 0
    assert all("Warszawa" in r.address or "Warsaw" in r.address for r in results)


# ---------------------------------------------------------------------------
# No-match fallback — never empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unrelated_query_returns_nonempty_sample(provider: MockMapsProvider) -> None:
    results = await provider.search_places("pizza tokyo ramen", 10)
    assert len(results) > 0


@pytest.mark.asyncio
async def test_fallback_sample_is_diverse(provider: MockMapsProvider) -> None:
    results = await provider.search_places("xyzzy_no_match", 10)
    categories = {r.category for r in results}
    assert len(categories) >= 3


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_query_returns_identical_results(provider: MockMapsProvider) -> None:
    a = await provider.search_places("marketing agencies Wrocław", 5)
    b = await provider.search_places("marketing agencies Wrocław", 5)
    assert [r.id for r in a] == [r.id for r in b]


@pytest.mark.asyncio
async def test_fallback_sample_is_deterministic(provider: MockMapsProvider) -> None:
    a = await provider.search_places("no_match_xyz", 6)
    b = await provider.search_places("no_match_xyz", 6)
    assert [r.id for r in a] == [r.id for r in b]


# ---------------------------------------------------------------------------
# get_place_details
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_place_details_returns_full_record(provider: MockMapsProvider) -> None:
    results = await provider.search_places("dental clinics Wrocław", 1)
    assert results
    details = await provider.get_place_details(results[0].id)
    assert details.id == results[0].id
    assert details.name == results[0].name
    assert details.rating is None
    assert details.review_count is None
    assert hasattr(details, "website")
    assert hasattr(details, "hours")


@pytest.mark.asyncio
async def test_get_place_details_unknown_id_raises_key_error(provider: MockMapsProvider) -> None:
    with pytest.raises(KeyError, match="Place not found"):
        await provider.get_place_details("nonexistent-id-xyz")
