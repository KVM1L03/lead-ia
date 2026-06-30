"""Shared Pydantic schemas used across microservices."""

from pydantic import BaseModel, ConfigDict


class PlaceSearchResult(BaseModel):
    model_config = ConfigDict(strict=True)

    id: str
    name: str
    address: str
    lat: float
    lng: float
    category: str
    rating: float
    review_count: int


class PlaceDetails(PlaceSearchResult):
    model_config = ConfigDict(strict=True)

    website: str | None = None
    phone: str | None = None
    hours: list[str] = []
    photos: list[str] = []
