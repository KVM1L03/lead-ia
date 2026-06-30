"""SerpAPI MapsProvider — Google Maps search via the SerpAPI HTTP API."""

import httpx
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from maps_bridge.errors import RateLimitError
from shared.schemas import PlaceDetails, PlaceSearchResult

_SERPAPI_URL = "https://serpapi.com/search"


def _looks_like_data_id(place_id: str) -> bool:
    return place_id.startswith("0x") and ":" in place_id


def _looks_like_google_place_id(place_id: str) -> bool:
    return place_id.startswith("ChI")


def _build_data_param(data_id: str, lat: float, lng: float) -> str:
    """SerpAPI requires a constructed `data` string when looking up by data_id."""
    return f"!4m5!3m4!1s{data_id}!8m2!3d{lat}!4d{lng}"


def _details_request_params(
    place_id: str,
    api_key: str,
    *,
    lat: float | None = None,
    lng: float | None = None,
) -> dict[str, str]:
    params: dict[str, str] = {"engine": "google_maps", "api_key": api_key, "hl": "en"}
    if _looks_like_google_place_id(place_id):
        params["place_id"] = place_id
    elif _looks_like_data_id(place_id):
        if lat is None or lng is None:
            raise ValueError(
                "data_id lookups require lat and lng — prefer place_id from search "
                "results, or pass lat/lng to get_place_details"
            )
        params["type"] = "place"
        params["data"] = _build_data_param(place_id, lat, lng)
    else:
        params["place_id"] = place_id
    return params


def _normalize_category(type_value: str | list[str]) -> str:
    if isinstance(type_value, list):
        return ", ".join(type_value) if type_value else ""
    return type_value


def _normalize_hours(hours: dict[str, str] | list[dict[str, str]]) -> list[str]:
    if isinstance(hours, dict):
        return [f"{day}: {time}" for day, time in hours.items()]
    normalized: list[str] = []
    for entry in hours:
        for day, time in entry.items():
            normalized.append(f"{day}: {time}")
    return normalized


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
    type: str | list[str] = ""
    rating: float = 0.0
    reviews: int = 0
    gps_coordinates: _Coords = Field(default_factory=_Coords)


class _SearchResponse(BaseModel):
    local_results: list[_LocalResult] = []


class _PlaceResult(BaseModel):
    title: str = ""
    address: str = ""
    type: str | list[str] = ""
    rating: float = 0.0
    reviews: int = 0
    gps_coordinates: _Coords = Field(default_factory=_Coords)
    website: str | None = None
    phone: str | None = None
    hours: dict[str, str] | list[dict[str, str]] = Field(default_factory=dict)


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
                id=item.place_id or item.data_id or "",
                name=item.title,
                address=item.address,
                lat=item.gps_coordinates.latitude,
                lng=item.gps_coordinates.longitude,
                category=_normalize_category(item.type),
                rating=item.rating,
                review_count=item.reviews,
            )
            for item in data.local_results[:limit]
        ]

    async def get_place_details(
        self,
        place_id: str,
        *,
        lat: float | None = None,
        lng: float | None = None,
    ) -> PlaceDetails:
        params = _details_request_params(place_id, self._api_key, lat=lat, lng=lng)
        raw = await self._get(params)
        data = _DetailsResponse.model_validate_json(raw)
        p = data.place_results
        return PlaceDetails(
            id=place_id,
            name=p.title,
            address=p.address,
            lat=p.gps_coordinates.latitude,
            lng=p.gps_coordinates.longitude,
            category=_normalize_category(p.type),
            rating=p.rating,
            review_count=p.reviews,
            website=p.website,
            phone=p.phone,
            hours=_normalize_hours(p.hours),
            photos=[],
        )
