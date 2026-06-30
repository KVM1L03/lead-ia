"""SQLite-backed response cache and transparent caching wrapper for MapsProvider."""

import hashlib
import json
import sqlite3
import time

from maps_bridge.providers import MapsProvider
from shared.schemas import PlaceDetails, PlaceSearchResult


class SQLiteCache:
    def __init__(self, db_path: str, ttl: int = 86400) -> None:
        self._db_path = db_path
        self._ttl = ttl
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS search_cache "
                "(key TEXT PRIMARY KEY, response TEXT NOT NULL, created_at INTEGER NOT NULL)"
            )
            conn.execute(
                "CREATE TABLE IF NOT EXISTS details_cache "
                "(key TEXT PRIMARY KEY, response TEXT NOT NULL, created_at INTEGER NOT NULL)"
            )

    @staticmethod
    def _search_key(query: str, limit: int) -> str:
        return hashlib.sha256(f"{query}:{limit}".encode()).hexdigest()

    # --- search ---

    def get_search(self, query: str, limit: int) -> str | None:
        key = self._search_key(query, limit)
        with self._connect() as conn:
            row = conn.execute(
                "SELECT response, created_at FROM search_cache WHERE key = ?", (key,)
            ).fetchone()
        if row is None:
            return None
        response: str = row[0]
        created_at: int = row[1]
        if time.time() - created_at > self._ttl:
            with self._connect() as conn:
                conn.execute("DELETE FROM search_cache WHERE key = ?", (key,))
            return None
        return response

    def set_search(self, query: str, limit: int, json_str: str) -> None:
        key = self._search_key(query, limit)
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO search_cache (key, response, created_at) VALUES (?, ?, ?)",
                (key, json_str, int(time.time())),
            )

    # --- details ---

    def get_details(self, place_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT response, created_at FROM details_cache WHERE key = ?", (place_id,)
            ).fetchone()
        if row is None:
            return None
        response: str = row[0]
        created_at: int = row[1]
        if time.time() - created_at > self._ttl:
            with self._connect() as conn:
                conn.execute("DELETE FROM details_cache WHERE key = ?", (place_id,))
            return None
        return response

    def set_details(self, place_id: str, json_str: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO details_cache (key, response, created_at) VALUES (?, ?, ?)",
                (place_id, json_str, int(time.time())),
            )

    # --- maintenance ---

    def evict_expired(self) -> None:
        cutoff = int(time.time()) - self._ttl
        with self._connect() as conn:
            conn.execute("DELETE FROM search_cache WHERE created_at < ?", (cutoff,))
            conn.execute("DELETE FROM details_cache WHERE created_at < ?", (cutoff,))


class CachingMapsProvider:
    """Transparent caching layer around any MapsProvider.

    The inner provider is unaware it is being cached.
    Only successful responses are stored; errors propagate unchanged.
    """

    def __init__(self, inner: MapsProvider, cache: SQLiteCache) -> None:
        self._inner = inner
        self._cache = cache

    async def search_places(self, query: str, limit: int) -> list[PlaceSearchResult]:
        cached = self._cache.get_search(query, limit)
        if cached is not None:
            items = json.loads(cached)
            return [PlaceSearchResult.model_validate(item) for item in items]
        results = await self._inner.search_places(query, limit)
        self._cache.set_search(query, limit, json.dumps([r.model_dump() for r in results]))
        return results

    async def get_place_details(self, place_id: str) -> PlaceDetails:
        cached = self._cache.get_details(place_id)
        if cached is not None:
            return PlaceDetails.model_validate_json(cached)
        details = await self._inner.get_place_details(place_id)
        self._cache.set_details(place_id, details.model_dump_json())
        return details
