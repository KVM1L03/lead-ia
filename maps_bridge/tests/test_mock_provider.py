import pytest
from pydantic import ValidationError

from maps_bridge.providers.mock import MockMapsProvider
from shared.schemas import PlaceSearchResult


@pytest.fixture
def provider() -> MockMapsProvider:
    return MockMapsProvider()


async def test_search_dental_respects_limit(provider: MockMapsProvider) -> None:
    results = await provider.search_places("dental", 5)
    assert len(results) <= 5
    assert all("dental" in r.category.lower() or "dental" in r.name.lower() for r in results)


async def test_search_dental_returns_all_when_limit_high(provider: MockMapsProvider) -> None:
    results = await provider.search_places("dental", 100)
    assert len(results) == 10


async def test_search_nonexistent_returns_empty(provider: MockMapsProvider) -> None:
    results = await provider.search_places("nonexistent_xyz_12345", 10)
    assert results == []


async def test_search_is_case_insensitive(provider: MockMapsProvider) -> None:
    lower = await provider.search_places("coffee", 100)
    upper = await provider.search_places("COFFEE", 100)
    assert len(lower) == len(upper) == 10


async def test_search_multi_word_query_matches_by_token(provider: MockMapsProvider) -> None:
    results = await provider.search_places("dental warsaw", 10)
    warsaw = [r for r in results if "warsaw" in r.id]
    assert len(warsaw) == 3


async def test_get_place_details_valid(provider: MockMapsProvider) -> None:
    results = await provider.search_places("dental", 1)
    assert results
    details = await provider.get_place_details(results[0].id)
    assert details.id == results[0].id
    assert details.name == results[0].name
    assert hasattr(details, "website")
    assert hasattr(details, "hours")


async def test_get_place_details_missing_raises_key_error(provider: MockMapsProvider) -> None:
    with pytest.raises(KeyError, match="Place not found"):
        await provider.get_place_details("missing-id-xyz")


def test_pydantic_strict_rejects_missing_required_field() -> None:
    # rating/review_count are now optional; omit a truly required field (name) instead
    with pytest.raises(ValidationError):
        PlaceSearchResult.model_validate(
            {
                "id": "bad",
                # name intentionally omitted — still required
                "address": "1 Bad Street",
                "lat": 51.5,
                "lng": -0.1,
                "category": "dental",
                "rating": 4.5,
                "review_count": 10,
            }
        )


def test_place_search_result_rating_optional() -> None:
    # rating and review_count may be absent (e.g. Google Places API New)
    r = PlaceSearchResult.model_validate(
        {
            "id": "no-rating",
            "name": "No Rating Place",
            "address": "1 Street",
            "lat": 51.5,
            "lng": -0.1,
            "category": "dental",
        }
    )
    assert r.rating is None
    assert r.review_count is None


def test_pydantic_strict_rejects_string_for_float_field() -> None:
    # strict=True in ConfigDict prevents str→float coercion
    with pytest.raises(ValidationError):
        PlaceSearchResult.model_validate(
            {
                "id": "bad",
                "name": "Bad Place",
                "address": "1 Bad Street",
                "lat": "51.5",
                "lng": -0.1,
                "category": "dental",
                "rating": 4.5,
                "review_count": 10,
            }
        )
