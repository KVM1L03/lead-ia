"""Tests for Settings config flags."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsError

from api_gateway.config import Settings


def test_defaults() -> None:
    s = Settings()
    assert s.PERSISTENCE_ENABLED is True
    assert s.EXECUTION_MODE == "temporal"
    assert s.RATE_LIMIT_BACKEND == "redis"
    assert s.DEMO_MAX_LEADS_SYNC == 25


def test_demo_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSISTENCE_ENABLED", "false")
    monkeypatch.setenv("EXECUTION_MODE", "sync")
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setenv("DEMO_MAX_LEADS_SYNC", "10")
    s = Settings()
    assert s.PERSISTENCE_ENABLED is False
    assert s.EXECUTION_MODE == "sync"
    assert s.RATE_LIMIT_BACKEND == "memory"
    assert s.DEMO_MAX_LEADS_SYNC == 10


def test_invalid_execution_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXECUTION_MODE", "batch")
    with pytest.raises((ValidationError, SettingsError)):
        Settings()


def test_invalid_rate_limit_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_BACKEND", "memcache")
    with pytest.raises((ValidationError, SettingsError)):
        Settings()
