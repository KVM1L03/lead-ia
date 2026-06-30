"""SerpAPI MapsProvider — Google Maps search via the SerpAPI HTTP API."""

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from maps_bridge.errors import RateLimitError
from shared.schemas import PlaceDetails, PlaceSearchResult

_SERPAPI_URL = "https://serpapi.com/search"


# ---------------------------------------------------------------------------
# Internal models for parsing SerpAPI responses (no strict mode — API is loose)
# ---------------------------------------------------------------------------


class _Coords(BaseModel):
    latitude: float = 0.0
    longitude: float = 0.0


class _LocalResult(BaseModel):
    data_id: str | None = None
    place_id: str | None = None
    title: str = ""
    address: str = ""
    type: str = ""
    rating: float = 0.0
    reviews: int = 0
    gps_coordinates: _Coords = Field(default_factory=_Coords)


class _SearchResponse(BaseModel):
    local_results: list[_LocalResult] = []


class _PlaceResult(BaseModel):
    title: str = ""
    address: str = ""
    type: str = ""
    rating: float = 0.0
    reviews: int = 0
    gps_coordinates: _Coords = Field(default_factory=_Coords)
    website: str | None = None
    phone: str | None = None
    hours: dict[str, str] = {}


class _DetailsResponse(BaseModel):
    place_results: _PlaceResult = Field(default_factory=_PlaceResult)


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class SerpAPIMapsProvider:
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None) -> None:
        self._api_key = api_key
        self._client = client or httpx.AsyncClient(timeout=10.0)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(httpx.TransportError),
        reraise=True,
    )
    async def _get(self, params: dict[str, str]) -> bytes:
        response = await self._client.get(_SERPAPI_URL, params=params)
        if response.status_code == 429:
            raise RateLimitError("SerpAPI rate limit exceeded (HTTP 429)")
        response.raise_for_status()
        return response.content

    async def search_places(self, query: str, limit: int) -> list[PlaceSearchResult]:
        params = {
            "engine": "google_maps",
            "q": query,
            "type": "search",
            "hl": "en",
            "gl": "us",
            "api_key": self._api_key,
        }
        raw = await self._get(params)
        data = _SearchResponse.model_validate_json(raw)
        return [
            PlaceSearchResult(
                id=item.data_id or item.place_id or "",
                name=item.title,
                address=item.address,
                lat=item.gps_coordinates.latitude,
                lng=item.gps_coordinates.longitude,
                category=item.type,
                rating=item.rating,
                review_count=item.reviews,
            )
            for item in data.local_results[:limit]
        ]

    async def get_place_details(self, place_id: str) -> PlaceDetails:
        params = {
            "engine": "google_maps",
            "type": "place",
            "data_id": place_id,
            "hl": "en",
            "api_key": self._api_key,
        }
        raw = await self._get(params)
        data = _DetailsResponse.model_validate_json(raw)
        p = data.place_results
        hours = [f"{day}: {time}" for day, time in p.hours.items()]
        return PlaceDetails(
            id=place_id,
            name=p.title,
            address=p.address,
            lat=p.gps_coordinates.latitude,
            lng=p.gps_coordinates.longitude,
            category=p.type,
            rating=p.rating,
            review_count=p.reviews,
            website=p.website,
            phone=p.phone,
            hours=hours,
            photos=[],
        )
