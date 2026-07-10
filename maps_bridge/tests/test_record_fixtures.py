"""Unit tests for scripts/record_fixtures.py.

Tests the dry-run path and --max-calls guard without making any HTTP calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import the script as a module (it adds the repo root to sys.path itself)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import record_fixtures  # noqa: E402, I001


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_FAKE_SEARCH_RESULT = MagicMock()
_FAKE_SEARCH_RESULT.id = "place-001"
_FAKE_SEARCH_RESULT.model_dump_json.return_value = json.dumps(
    {
        "id": "place-001",
        "name": "Test Place",
        "address": "ul. Testowa 1, Wrocław",
        "lat": 51.1,
        "lng": 17.0,
        "category": "dental",
        "rating": None,
        "review_count": None,
    }
)

_FAKE_DETAILS = MagicMock()
_FAKE_DETAILS.model_dump_json.return_value = json.dumps(
    {
        "id": "place-001",
        "name": "Test Place",
        "address": "ul. Testowa 1, Wrocław",
        "lat": 51.1,
        "lng": 17.0,
        "category": "dental",
        "rating": None,
        "review_count": None,
        "website": "https://example.pl",
        "phone": "+48 71 000 0000",
        "hours": [],
        "photos": [],
    }
)


def _make_provider(search_results: list, details_result: object) -> MagicMock:
    provider = MagicMock()
    provider.search_places = AsyncMock(return_value=search_results)
    provider.get_place_details = AsyncMock(return_value=details_result)
    return provider


# ---------------------------------------------------------------------------
# Tests: dry-run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dry_run_prints_plan_and_makes_no_calls(capsys: pytest.CaptureFixture) -> None:
    queries = [("dental clinics Wrocław", 3)]
    await record_fixtures.record(
        queries=queries,
        api_key="fake-key",
        max_calls=100,
        dry_run=True,
        verbose=False,
    )
    out = capsys.readouterr().out
    assert "[DRY RUN]" in out
    assert "dental clinics Wrocław" in out


@pytest.mark.asyncio
async def test_dry_run_does_not_write_files(tmp_path: Path) -> None:
    with patch.object(record_fixtures, "OUTPUT_DIR", tmp_path):
        await record_fixtures.record(
            queries=[("test query", 2)],
            api_key="fake-key",
            max_calls=100,
            dry_run=True,
            verbose=False,
        )
    # No files written
    assert list(tmp_path.rglob("*.json")) == []


@pytest.mark.asyncio
async def test_dry_run_does_not_call_provider(capsys: pytest.CaptureFixture) -> None:
    provider_mock = _make_provider([_FAKE_SEARCH_RESULT], _FAKE_DETAILS)
    with patch(
        "maps_bridge.providers.google_places.GooglePlacesProvider", return_value=provider_mock
    ):
        await record_fixtures.record(
            queries=[("dental clinics Wrocław", 2)],
            api_key="fake-key",
            max_calls=100,
            dry_run=True,
            verbose=False,
        )
    provider_mock.search_places.assert_not_called()
    provider_mock.get_place_details.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: _estimate_calls
# ---------------------------------------------------------------------------


def test_estimate_calls_single_query() -> None:
    assert record_fixtures._estimate_calls([("q", 5)]) == 6  # 1 search + 5 details


def test_estimate_calls_multiple_queries() -> None:
    queries = [("a", 3), ("b", 2)]
    assert record_fixtures._estimate_calls(queries) == (1 + 3) + (1 + 2)


# ---------------------------------------------------------------------------
# Tests: --max-calls guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_calls_aborts_before_any_calls_when_estimate_exceeds_limit(
    capsys: pytest.CaptureFixture,
) -> None:
    """Estimated calls > max_calls → sys.exit(1) before any network call."""
    queries = [("query a", 10), ("query b", 10)]  # estimate = 22 calls
    provider_mock = _make_provider([_FAKE_SEARCH_RESULT], _FAKE_DETAILS)

    with (
        patch.object(record_fixtures, "GooglePlacesProvider", return_value=provider_mock),
        patch("builtins.input", return_value="y"),
        pytest.raises(SystemExit) as exc_info,
    ):
        await record_fixtures.record(
            queries=queries,
            api_key="fake-key",
            max_calls=5,  # less than estimate of 22
            dry_run=False,
            verbose=False,
        )

    assert exc_info.value.code == 1
    provider_mock.search_places.assert_not_called()


@pytest.mark.asyncio
async def test_max_calls_aborts_mid_run_on_details(tmp_path: Path) -> None:
    """max_calls guard in the details loop stops fetching when limit is hit mid-run.

    Setup: limit=2, max_calls=3 (estimate=3, exactly at limit → pre-check passes).
    The mocked provider returns 3 results (more than limit), so the estimate
    underestimates actuals.  After 1 search + 2 details (3 calls total), the
    check for the 3rd detail sees call_count+1=4 > max_calls=3 and breaks.
    """
    results = []
    for i in range(3):  # 3 results despite limit=2
        r = MagicMock()
        r.id = f"place-{i:03d}"
        r.model_dump_json.return_value = json.dumps(
            {
                "id": f"place-{i:03d}",
                "name": f"Place {i}",
                "address": "addr",
                "lat": 0.0,
                "lng": 0.0,
                "category": "test",
                "rating": None,
                "review_count": None,
            }
        )
        results.append(r)

    provider_mock = _make_provider(results, _FAKE_DETAILS)

    with (
        patch.object(record_fixtures, "OUTPUT_DIR", tmp_path),
        patch.object(record_fixtures, "GooglePlacesProvider", return_value=provider_mock),
        patch("builtins.input", return_value="y"),
    ):
        # limit=2 → estimate=3=max_calls (pre-check: 3 > 3 is False, passes)
        await record_fixtures.record(
            queries=[("query", 2)],
            api_key="fake-key",
            max_calls=3,
            dry_run=False,
            verbose=False,
        )

    # Search was called once
    provider_mock.search_places.assert_called_once()
    # Only 2 detail calls: 3rd result is skipped when call_count+1 > max_calls
    assert provider_mock.get_place_details.call_count == 2


# ---------------------------------------------------------------------------
# Tests: user aborts at confirmation prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_declines_confirmation_exits(capsys: pytest.CaptureFixture) -> None:
    provider_mock = _make_provider([_FAKE_SEARCH_RESULT], _FAKE_DETAILS)
    with (
        patch.object(record_fixtures, "GooglePlacesProvider", return_value=provider_mock),
        patch("builtins.input", return_value="n"),
        pytest.raises(SystemExit) as exc_info,
    ):
        await record_fixtures.record(
            queries=[("query", 2)],
            api_key="fake-key",
            max_calls=100,
            dry_run=False,
            verbose=False,
        )
    assert exc_info.value.code == 0
    provider_mock.search_places.assert_not_called()


# ---------------------------------------------------------------------------
# Tests: slug helper
# ---------------------------------------------------------------------------


def test_slug_replaces_non_alphanum() -> None:
    assert record_fixtures._slug("dental clinics Wrocław") == "dental_clinics_wroc_aw"


def test_slug_strips_leading_trailing_underscores() -> None:
    slug = record_fixtures._slug("  hello world  ")
    assert not slug.startswith("_")
    assert not slug.endswith("_")


# ---------------------------------------------------------------------------
# Tests: API key not leaked into fixture files
# ---------------------------------------------------------------------------


def test_assert_no_key_in_file_raises_and_deletes(tmp_path: Path) -> None:
    f = tmp_path / "fixture.json"
    api_key = "AIzaSy_FAKE_KEY_12345"
    f.write_text(f'{{"key": "{api_key}"}}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="API key found"):
        record_fixtures._assert_no_key_in_file(f, api_key)

    assert not f.exists()  # deleted by the guard


def test_assert_no_key_in_file_passes_when_clean(tmp_path: Path) -> None:
    f = tmp_path / "fixture.json"
    f.write_text('{"name": "Test"}', encoding="utf-8")
    record_fixtures._assert_no_key_in_file(f, "AIzaSy_FAKE_KEY_12345")  # should not raise
