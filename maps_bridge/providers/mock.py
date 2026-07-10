"""Mock MapsProvider — serves recorded Google Places fixtures.

Loads data from maps_bridge/fixtures/recorded/ on first call (lazy, cached).
Matching strategy for search_places:
  1. Exact/near:  incoming query tokens are a subset or superset of a recorded
                  query's tokens → return that recorded result set.
  2. Fuzzy:       score each recorded query by token overlap (Jaccard); pick
                  the highest-scoring entry (score > 0).
  3. No match:    return one place per recorded category (deterministic round-
                  robin by slug), up to `limit`.

Fallback is signaled via logging.warning — no schema change required.
Limitation: the HTTP response cannot carry match confidence without a wrapper
schema addition outside the MapsProvider Protocol contract (T-RR.3 task).
"""

import json
import logging
from functools import lru_cache
from pathlib import Path

from shared.schemas import PlaceDetails, PlaceSearchResult

_FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "recorded"
_logger = logging.getLogger(__name__)


def _tokenize(text: str) -> frozenset[str]:
    return frozenset(t for t in text.lower().split() if len(t) > 1)


@lru_cache(maxsize=1)
def _load_fixtures() -> tuple[
    dict[str, list[PlaceSearchResult]],
    dict[str, PlaceDetails],
    list[str],
    dict[str, str],
]:
    manifest = json.loads((_FIXTURE_DIR / "manifest.json").read_text(encoding="utf-8"))

    search_index: dict[str, list[PlaceSearchResult]] = {}
    details_index: dict[str, PlaceDetails] = {}
    slugs: list[str] = []
    slug_to_query: dict[str, str] = {}

    for entry in manifest["queries"]:
        slug: str = entry["slug"]
        query: str = entry["query"]
        slugs.append(slug)
        slug_to_query[slug] = query

        raw = json.loads((_FIXTURE_DIR / "search" / f"{slug}.json").read_text(encoding="utf-8"))
        search_index[slug] = [PlaceSearchResult.model_validate(r) for r in raw]

        for place_id in entry["detail_ids"]:
            if place_id not in details_index:
                details_index[place_id] = PlaceDetails.model_validate_json(
                    (_FIXTURE_DIR / "details" / f"{place_id}.json").read_text(encoding="utf-8")
                )

    return search_index, details_index, slugs, slug_to_query


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _best_match(
    query_tokens: frozenset[str],
    slugs: list[str],
    slug_to_query: dict[str, str],
) -> tuple[str | None, float]:
    best_slug: str | None = None
    best_score: float = 0.0
    for slug in slugs:
        recorded = _tokenize(slug_to_query[slug])
        score = _jaccard(query_tokens, recorded)
        if query_tokens and query_tokens <= recorded:
            score = 1.0
        elif recorded and recorded <= query_tokens:
            score = 1.0
        if score > best_score or (score == best_score and best_slug is not None and slug < best_slug):
            best_score = score
            best_slug = slug
    return best_slug, best_score


def _fallback_sample(
    search_index: dict[str, list[PlaceSearchResult]],
    slugs: list[str],
    limit: int,
) -> list[PlaceSearchResult]:
    """One place from each recorded category, in manifest order, up to limit."""
    sample: list[PlaceSearchResult] = []
    for slug in slugs:
        if search_index[slug]:
            sample.append(search_index[slug][0])
        if len(sample) >= limit:
            break
    return sample[:limit]


class MockMapsProvider:
    async def search_places(self, query: str, limit: int) -> list[PlaceSearchResult]:
        search_index, _, slugs, slug_to_query = _load_fixtures()
        query_tokens = _tokenize(query)
        best_slug, best_score = _best_match(query_tokens, slugs, slug_to_query)

        if best_slug is not None and best_score >= 1.0:
            return search_index[best_slug][:limit]

        if best_slug is not None and best_score > 0.0:
            _logger.warning(
                "mock_provider: fuzzy match for %r → %r (score=%.2f); "
                "returning recorded results for that query",
                query,
                slug_to_query[best_slug],
                best_score,
            )
            return search_index[best_slug][:limit]

        _logger.warning(
            "mock_provider: no match for %r; returning representative sample",
            query,
        )
        return _fallback_sample(search_index, slugs, limit)

    async def get_place_details(self, place_id: str) -> PlaceDetails:
        _, details_index, _, _ = _load_fixtures()
        if place_id not in details_index:
            raise KeyError(f"Place not found: {place_id!r}")
        return details_index[place_id]
