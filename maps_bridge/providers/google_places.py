"""Google Places API (New) MapsProvider — Text Search + Place Details.

Uses the Places API (New) endpoints (not the legacy Places API, which is
closed to new projects). Authentication via X-Goog-Api-Key header.
"""

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from maps_bridge.errors import RateLimitError
from shared.schemas import PlaceDetails, PlaceSearchResult

_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

# ---------------------------------------------------------------------------
# FieldMasks — billing tier control
#
# Places API (New) bills at the HIGHEST SKU tier among requested fields.
#
# Text Search tiers (per call):
#   Pro tier   (5 000 free/month): core fields — id, displayName, formattedAddress,
#              location, primaryType, types, photos, businessStatus, …
#   Enterprise (1 000 free/month): operational fields — rating, userRatingCount,
#              reviews, currentOpeningHours, websiteUri, nationalPhoneNumber, …
#
# NEVER add places.rating, places.userRatingCount, places.reviews, or any
# atmosphere field to _SEARCH_MASK.  One forgotten field silently upgrades
# every search call to Enterprise — 5× smaller free quota with no warning.
# test_google_places_provider.py::test_search_mask_excludes_rating_and_reviews
# enforces this invariant automatically.
# ---------------------------------------------------------------------------
_SEARCH_MASK = (
    "places.id,"
    "places.displayName,"
    "places.formattedAddress,"
    "places.location,"
    "places.primaryType,"
    "places.types"
)

# Place Details tiers (per call):
#   Basic tier   : id, displayName, formattedAddress, location, primaryType, types, …
#   Advanced tier: websiteUri, nationalPhoneNumber, regularOpeningHours,
#                  currentOpeningHours, rating, priceLevel, …   ← we land here
#   Preferred    : reviews, editorialSummary, atmosphere fields
#
# websiteUri is required by the qualifier's has_website ICP criterion, so Place
# Details calls use the Advanced tier.  rating is also in the Advanced tier —
# but we still exclude it: the provider contract requires rating=None (schema
# invariant T-GP.1), and omitting it does no harm given we are already at Advanced.
_DETAILS_MASK = (
    "id,"
    "displayName,"
    "formattedAddress,"
    "location,"
    "primaryType,"
    "types,"
    "websiteUri,"
    "nationalPhoneNumber,"
    "regularOpeningHours"
)

# ---------------------------------------------------------------------------
# Internal Pydantic models (loose — API shape may vary; no strict mode)
# ---------------------------------------------------------------------------

_GENERIC_TYPES = frozenset({
    "point_of_interest",
    "establishment",
    "store",
    "food",
    "premise",
    "route",
    "locality",
    "political",
})


def _pick_category(primary_type: str | None, types: list[str]) -> str:
    """Return a single human-readable category from the Google Places types list."""
    if primary_type:
        return primary_type.replace("_", " ").title()
    for t in types:
        if t not in _GENERIC_TYPES:
            return t.replace("_", " ").title()
    return types[0].replace("_", " ").title() if types else ""


class _LocalizedText(BaseModel):
    text: str = ""
    languageCode: str = ""


class _LatLng(BaseModel):
    latitude: float = 0.0
    longitude: float = 0.0


class _OpeningHours(BaseModel):
    weekdayDescriptions: list[str] = []


class _Place(BaseModel):
    id: str = ""
    displayName: _LocalizedText = Field(default_factory=_LocalizedText)
    formattedAddress: str = ""
    location: _LatLng = Field(default_factory=_LatLng)
    primaryType: str | None = None
    types: list[str] = []
    websiteUri: str | None = None
    nationalPhoneNumber: str | None = None
    regularOpeningHours: _OpeningHours | None = None


class _SearchResponse(BaseModel):
    places: list[_Place] = []


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class GooglePlacesProvider:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=10.0)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
        reraise=True,
    )
    async def _request(
        self,
        method: str,
        url: str,
        *,
        field_mask: str,
        body: dict[str, object] | None = None,
    ) -> bytes:
        response = await self._client.request(
            method,
            url,
            json=body,
            headers={
                "X-Goog-Api-Key": self._api_key,
                "X-Goog-FieldMask": field_mask,
            },
        )
        if response.status_code == 429:
            raise RateLimitError("Google Places API rate limit exceeded (HTTP 429)")
        if response.status_code in (400, 401, 403):
            raise ValueError(
                f"Google Places API auth/billing error ({response.status_code}). "
                "Check GOOGLE_MAPS_API_KEY, billing is enabled, and the Places API "
                f"(New) is activated. Response: {response.text[:300]}"
            )
        response.raise_for_status()
        return response.content

    async def search_places(self, query: str, limit: int) -> list[PlaceSearchResult]:
        raw = await self._request(
            "POST",
            _SEARCH_URL,
            field_mask=_SEARCH_MASK,
            body={"textQuery": query, "maxResultCount": min(limit, 20)},
        )
        data = _SearchResponse.model_validate_json(raw)
        return [
            PlaceSearchResult(
                id=place.id,
                name=place.displayName.text,
                address=place.formattedAddress,
                lat=place.location.latitude,
                lng=place.location.longitude,
                category=_pick_category(place.primaryType, place.types),
                rating=None,        # excluded from FieldMask — see _SEARCH_MASK comment
                review_count=None,  # excluded from FieldMask — see _SEARCH_MASK comment
            )
            for place in data.places[:limit]
        ]

    async def get_place_details(self, place_id: str) -> PlaceDetails:
        url = _DETAILS_URL.format(place_id=place_id)
        raw = await self._request("GET", url, field_mask=_DETAILS_MASK)
        place = _Place.model_validate_json(raw)
        return PlaceDetails(
            id=place_id,
            name=place.displayName.text,
            address=place.formattedAddress,
            lat=place.location.latitude,
            lng=place.location.longitude,
            category=_pick_category(place.primaryType, place.types),
            rating=None,        # excluded from FieldMask — see _DETAILS_MASK comment
            review_count=None,  # excluded from FieldMask — see _DETAILS_MASK comment
            website=place.websiteUri,
            phone=place.nationalPhoneNumber,
            hours=(
                place.regularOpeningHours.weekdayDescriptions
                if place.regularOpeningHours
                else []
            ),
            photos=[],
        )
