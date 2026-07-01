"""Tests for Temporal activities.

All tests use mocked MCP / DSPy calls — no real API or network calls.
ActivityEnvironment runs activities in-process without Temporal server.
"""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from temporalio.testing import ActivityEnvironment

import ai_worker.activities as act
from ai_worker.activities import (
    generate_email_activity,
    qualify_lead_activity,
    search_places_activity,
)
from shared.schemas import (
    GeneratedEmail,
    PlaceDetails,
    PlaceSearchResult,
    QualifierVerdict,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

_PLACE = PlaceDetails(
    id="dental-warsaw-001",
    name="Klinika Stomatologiczna Centrum",
    address="ul. Nowy Swiat 28, Warszawa",
    lat=52.233,
    lng=21.021,
    category="dental",
    rating=4.8,
    review_count=187,
    website="https://dental-centrum.pl",
    phone="+48 22 826 1234",
    hours=["Mon-Fri 8:00-20:00"],
    photos=[],
)

_RESULT = PlaceSearchResult(
    id="dental-warsaw-001",
    name="Klinika Stomatologiczna Centrum",
    address="ul. Nowy Swiat 28, Warszawa",
    lat=52.233,
    lng=21.021,
    category="dental",
    rating=4.8,
    review_count=187,
)

_VERDICT = QualifierVerdict(
    is_qualified=True,
    score=0.88,
    reasoning="Dental clinic with website — strong ICP fit.",
    icp_fit={"is_b2b": True, "has_website": True, "size_match": False},
)

_EMAIL = GeneratedEmail(
    subject="Quick question about recalls at Klinika Centrum",
    body="Hi, saw your 4.8-star rating — impressive. We help dental clinics automate patient recalls. Worth a quick call?",
    personalization_hooks=["4.8-star rating", "Warsaw", "dental clinic"],
    model_used="anthropic/claude-sonnet-4-6",
)


def _mock_lm() -> MagicMock:
    lm = MagicMock()
    lm.model = "mock/test"
    return lm


# ---------------------------------------------------------------------------
# search_places_activity
# ---------------------------------------------------------------------------


async def test_search_places_returns_place_list(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    monkeypatch.setattr(act, "_call_search_places", AsyncMock(return_value=[_RESULT]))

    result = await env.run(search_places_activity, "dental Warsaw", 5)

    assert result == [_RESULT]
    act._call_search_places.assert_called_once_with("dental Warsaw", 5)  # type: ignore[attr-defined]


async def test_search_places_passes_limit_to_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    mock = AsyncMock(return_value=[_RESULT, _RESULT])
    monkeypatch.setattr(act, "_call_search_places", mock)

    await env.run(search_places_activity, "dentist", 10)

    mock.assert_called_once_with("dentist", 10)


async def test_search_places_propagates_mcp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    monkeypatch.setattr(
        act, "_call_search_places", AsyncMock(side_effect=RuntimeError("MCP server down"))
    )

    with pytest.raises(RuntimeError, match="MCP server down"):
        await env.run(search_places_activity, "q", 1)


# ---------------------------------------------------------------------------
# qualify_lead_activity
# ---------------------------------------------------------------------------


async def test_qualify_lead_returns_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    monkeypatch.setattr(act, "qualify_lead", lambda *a, **kw: _VERDICT)
    monkeypatch.setattr(act, "get_lm", lambda _role: _mock_lm())

    result = await env.run(qualify_lead_activity, "B2B dental software", _PLACE)

    assert result == _VERDICT
    assert result.is_qualified is True


async def test_qualify_lead_passes_outreach_goal(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    captured: dict[str, Any] = {}

    def _capture(goal: str, place: PlaceDetails, *, lm: Any) -> QualifierVerdict:
        captured["goal"] = goal
        return _VERDICT

    monkeypatch.setattr(act, "qualify_lead", _capture)
    monkeypatch.setattr(act, "get_lm", lambda _role: _mock_lm())

    await env.run(qualify_lead_activity, "plumbing SaaS", _PLACE)

    assert captured["goal"] == "plumbing SaaS"


async def test_qualify_lead_propagates_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ValidationError propagates so Temporal marks the attempt non-retryable."""
    from pydantic import ValidationError

    env = ActivityEnvironment()

    def _bad_qualify(*a: Any, **kw: Any) -> None:
        # Trigger a real ValidationError through schema validation
        QualifierVerdict.model_validate({"is_qualified": "yes", "score": 99})

    monkeypatch.setattr(act, "qualify_lead", _bad_qualify)
    monkeypatch.setattr(act, "get_lm", lambda _role: _mock_lm())

    with pytest.raises(ValidationError):
        await env.run(qualify_lead_activity, "goal", _PLACE)


async def test_qualify_lead_propagates_rate_limit_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rate-limit errors surface so Temporal can schedule a retry attempt."""
    env = ActivityEnvironment()

    def _rate_limited(*a: Any, **kw: Any) -> None:
        raise RuntimeError("rate limit exceeded")

    monkeypatch.setattr(act, "qualify_lead", _rate_limited)
    monkeypatch.setattr(act, "get_lm", lambda _role: _mock_lm())

    with pytest.raises(RuntimeError, match="rate limit"):
        await env.run(qualify_lead_activity, "goal", _PLACE)


# ---------------------------------------------------------------------------
# generate_email_activity
# ---------------------------------------------------------------------------


async def test_generate_email_returns_email(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    monkeypatch.setattr(act, "generate_email", lambda *a, **kw: _EMAIL)
    monkeypatch.setattr(act, "get_lm", lambda _role: _mock_lm())

    result = await env.run(
        generate_email_activity, "B2B dental software", _PLACE, _VERDICT, "I run SaaS."
    )

    assert result == _EMAIL
    assert len(result.personalization_hooks) > 0


async def test_generate_email_passes_sender_context(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    captured: dict[str, Any] = {}

    def _capture(*a: Any, **kw: Any) -> GeneratedEmail:
        captured.update(kw)
        return _EMAIL

    monkeypatch.setattr(act, "generate_email", _capture)
    monkeypatch.setattr(act, "get_lm", lambda _role: _mock_lm())

    await env.run(generate_email_activity, "goal", _PLACE, _VERDICT, "Sender: Jane, value prop: X")

    assert captured["sender_context"] == "Sender: Jane, value prop: X"
    assert captured["qualifier_reasoning"] == _VERDICT.reasoning


async def test_generate_email_propagates_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()

    def _fail(*a: Any, **kw: Any) -> None:
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(act, "generate_email", _fail)
    monkeypatch.setattr(act, "get_lm", lambda _role: _mock_lm())

    with pytest.raises(RuntimeError, match="LLM unavailable"):
        await env.run(generate_email_activity, "goal", _PLACE, _VERDICT, "sender")


# ---------------------------------------------------------------------------
# Module-level sanity checks
# ---------------------------------------------------------------------------


def test_activities_importable_without_side_effects() -> None:
    """Importing the module must not trigger MCP calls or LM construction."""
    import importlib

    importlib.import_module("ai_worker.activities")


def test_timeout_constants_are_set() -> None:
    assert act.SEARCH_TIMEOUT.total_seconds() == 60
    assert act.QUALIFY_TIMEOUT.total_seconds() == 30
    assert act.EMAIL_TIMEOUT.total_seconds() == 60


def test_retry_policies_have_non_retryable_validation_error() -> None:
    for policy in (act.SEARCH_RETRY, act.QUALIFY_RETRY, act.EMAIL_RETRY):
        assert policy.non_retryable_error_types is not None
        assert "ValidationError" in policy.non_retryable_error_types
