"""Tests that SQLiteCache keys are provider-scoped — no cross-provider pollution."""

from pathlib import Path

from maps_bridge.cache import SQLiteCache


def test_different_prefixes_do_not_share_entries(tmp_path: Path) -> None:
    db = str(tmp_path / "shared.db")
    serpapi_cache = SQLiteCache(db_path=db, prefix="serpapi")
    gp_cache = SQLiteCache(db_path=db, prefix="google_places")

    serpapi_cache.set_search("dentist warsaw", 5, '[{"serpapi": true}]')

    assert gp_cache.get_search("dentist warsaw", 5) is None


def test_same_prefix_shares_entries(tmp_path: Path) -> None:
    db = str(tmp_path / "shared.db")
    c1 = SQLiteCache(db_path=db, prefix="serpapi")
    c2 = SQLiteCache(db_path=db, prefix="serpapi")

    c1.set_search("query", 3, '"data"')
    assert c2.get_search("query", 3) == '"data"'


def test_details_different_prefixes_do_not_share(tmp_path: Path) -> None:
    db = str(tmp_path / "shared.db")
    c1 = SQLiteCache(db_path=db, prefix="serpapi")
    c2 = SQLiteCache(db_path=db, prefix="google_places")

    c1.set_details("ChIJtest001", '{"serpapi": true}')
    assert c2.get_details("ChIJtest001") is None


def test_empty_prefix_is_backward_compatible(tmp_path: Path) -> None:
    db = str(tmp_path / "backward.db")
    c = SQLiteCache(db_path=db)
    c.set_search("q", 1, '"old"')
    assert c.get_search("q", 1) == '"old"'
