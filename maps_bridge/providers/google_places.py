"""Google Places API (New) MapsProvider — Text Search + Place Details.

Uses the Places API (New) endpoints (not the legacy Places API, which is
closed to new projects). Authentication via X-Goog-Api-Key header.
"""

import asyncio
import logging

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from maps_bridge.errors import RateLimitError
from shared.schemas import PlaceDetails, PlaceSearchResult

_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"

_MAX_PAGE_SIZE = 20  # Google Places (New) Text Search hard cap per call
_PAGE_TOKEN_RETRY_ATTEMPTS = 3  # bounded retry while nextPageToken becomes valid

_logger = logging.getLogger(__name__)

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
# every search call to Enterprise — 5x smaller free quota with no warning.
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

_GENERIC_TYPES = frozenset(
    {
        "point_of_interest",
        "establishment",
        "store",
        "food",
        "premise",
        "route",
        "locality",
        "political",
    }
)


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
    languageCode: str = ""  # noqa: N815


class _LatLng(BaseModel):
    latitude: float = 0.0
    longitude: float = 0.0


class _OpeningHours(BaseModel):
    weekdayDescriptions: list[str] = []  # noqa: N815


class _Place(BaseModel):
    id: str = ""
    displayName: _LocalizedText = Field(default_factory=_LocalizedText)  # noqa: N815
    formattedAddress: str = ""  # noqa: N815
    location: _LatLng = Field(default_factory=_LatLng)
    primaryType: str | None = None  # noqa: N815
    types: list[str] = []
    websiteUri: str | None = None  # noqa: N815
    nationalPhoneNumber: str | None = None  # noqa: N815
    regularOpeningHours: _OpeningHours | None = None  # noqa: N815


class _SearchResponse(BaseModel):
    places: list[_Place] = []
    nextPageToken: str | None = None  # noqa: N815


class _PageTokenNotReadyError(Exception):
    """Raised when Google returns HTTP 400 on a request carrying a not-yet-valid pageToken.

    Google's docs note a short delay before a freshly-issued nextPageToken becomes
    usable. A 400 on a token-bearing request is treated as "not ready yet" and
    retried with backoff — distinct from a 400 on the first page, which is a real
    auth/billing error handled by the existing ValueError path below.
    """


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class GooglePlacesProvider:
    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        max_pages: int = 5,
        page_token_delay: float = 2.0,
    ) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._max_pages = max_pages
        self._page_token_delay = page_token_delay

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
        treat_400_as_token_not_ready: bool = False,
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
        if response.status_code == 400 and treat_400_as_token_not_ready:
            raise _PageTokenNotReadyError(
                "Google Places nextPageToken not yet valid (HTTP 400 on paginated request)"
            )
        if response.status_code in (400, 401, 403):
            raise ValueError(
                f"Google Places API auth/billing error ({response.status_code}). "
                "Check GOOGLE_MAPS_API_KEY, billing is enabled, and the Places API "
                f"(New) is activated. Response: {response.text[:300]}"
            )
        response.raise_for_status()
        return response.content

    async def _request_page(self, body: dict[str, object], *, has_token: bool) -> bytes:
        """Fetch one Text Search page.

        When the request carries a pageToken, retry with backoff on a 400 rather
        than treating it as a hard failure — Google's docs warn of a short delay
        before a freshly-issued token becomes valid.
        """
        if not has_token:
            return await self._request("POST", _SEARCH_URL, field_mask=_SEARCH_MASK, body=body)
        last_error: _PageTokenNotReadyError | None = None
        for attempt in range(1, _PAGE_TOKEN_RETRY_ATTEMPTS + 1):
            await asyncio.sleep(self._page_token_delay * attempt)
            try:
                return await self._request(
                    "POST",
                    _SEARCH_URL,
                    field_mask=_SEARCH_MASK,
                    body=body,
                    treat_400_as_token_not_ready=True,
                )
            except _PageTokenNotReadyError as exc:
                last_error = exc
        assert last_error is not None
        raise last_error

    async def search_places(self, query: str, limit: int) -> list[PlaceSearchResult]:
        collected: list[_Place] = []
        page_token: str | None = None
        pages_fetched = 0
        while True:
            page_size = min(limit - len(collected), _MAX_PAGE_SIZE)
            body: dict[str, object] = {"textQuery": query, "maxResultCount": page_size}
            if page_token:
                body["pageToken"] = page_token
            raw = await self._request_page(body, has_token=bool(page_token))
            data = _SearchResponse.model_validate_json(raw)
            collected.extend(data.places)
            pages_fetched += 1
            page_token = data.nextPageToken
            if len(collected) >= limit or not page_token or pages_fetched >= self._max_pages:
                break
        _logger.info(
            "google_places search: pages=%d results=%d query=%r limit=%d",
            pages_fetched,
            len(collected),
            query,
            limit,
        )
        return [
            PlaceSearchResult(
                id=place.id,
                name=place.displayName.text,
                address=place.formattedAddress,
                lat=place.location.latitude,
                lng=place.location.longitude,
                category=_pick_category(place.primaryType, place.types),
                rating=None,  # excluded from FieldMask — see _SEARCH_MASK comment
                review_count=None,  # excluded from FieldMask — see _SEARCH_MASK comment
            )
            for place in collected[:limit]
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
            rating=None,  # excluded from FieldMask — see _DETAILS_MASK comment
            review_count=None,  # excluded from FieldMask — see _DETAILS_MASK comment
            website=place.websiteUri,
            phone=place.nationalPhoneNumber,
            hours=(
                place.regularOpeningHours.weekdayDescriptions if place.regularOpeningHours else []
            ),
            photos=[],
        )
