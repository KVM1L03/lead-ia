"""Mock MapsProvider — serves fixture data, no network calls required."""

import json
from pathlib import Path

from shared.schemas import PlaceDetails, PlaceSearchResult

_FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "places.json"


def _load_fixtures() -> dict[str, PlaceDetails]:
    data = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    places: dict[str, PlaceDetails] = {}
    for item in data:
        place = PlaceDetails.model_validate(item)
        places[place.id] = place
    return places


_PLACES: dict[str, PlaceDetails] = _load_fixtures()


class MockMapsProvider:
    async def search_places(self, query: str, limit: int) -> list[PlaceSearchResult]:
        tokens = [t for t in query.lower().split() if t]
        search_fields = set(PlaceSearchResult.model_fields)
        matches = [
            PlaceSearchResult.model_validate(p.model_dump(include=search_fields))
            for p in _PLACES.values()
            if not tokens
            or any(
                tok in p.name.lower() or tok in p.category.lower() or tok in p.address.lower()
                for tok in tokens
            )
        ]
        return matches[:limit]

    async def get_place_details(self, place_id: str) -> PlaceDetails:
        if place_id not in _PLACES:
            raise KeyError(f"Place not found: {place_id!r}")
        return _PLACES[place_id]
