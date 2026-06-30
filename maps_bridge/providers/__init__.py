from typing import Protocol

from shared.schemas import PlaceDetails, PlaceSearchResult


class MapsProvider(Protocol):
    async def search_places(self, query: str, limit: int) -> list[PlaceSearchResult]: ...
    async def get_place_details(self, place_id: str) -> PlaceDetails: ...
