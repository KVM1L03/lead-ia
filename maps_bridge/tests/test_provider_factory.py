"""Tests for maps provider construction and injection."""

from __future__ import annotations

from pathlib import Path

import pytest

from maps_bridge.cache import CachingMapsProvider
from maps_bridge.config import settings
from maps_bridge.provider_factory import get_provider
from maps_bridge.providers.mock import MockMapsProvider


def test_get_provider_uses_requested_name_not_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Passing provider_name='serpapi' must not consult settings.MAPS_PROVIDER."""
    monkeypatch.setattr(settings, "MAPS_PROVIDER", "mock")
    monkeypatch.setattr(settings, "SERPAPI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "CACHE_DB_PATH", str(tmp_path / "cache.db"))

    provider = get_provider("serpapi")

    assert isinstance(provider, CachingMapsProvider)
    assert not isinstance(provider, MockMapsProvider)


def test_get_provider_mock_does_not_require_settings_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MAPS_PROVIDER", "google_places")
    provider = get_provider("mock")
    assert isinstance(provider, MockMapsProvider)
