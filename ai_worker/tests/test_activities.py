"""Tests for Temporal activities.

Activities are thin wrappers — test that they correctly delegate to graph nodes.
All tests use ActivityEnvironment (no live Temporal server needed).
"""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from temporalio.testing import ActivityEnvironment

import ai_worker.activities as act
from ai_worker.activities import (
    expand_search_query_activity,
    generate_email_activity,
    qualify_lead_activity,
    search_places_activity,
)
from ai_worker.agent_graph import LeadProcessingState
from shared.schemas import (
    ExpansionDecision,
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

_EXPANSION_DECISION = ExpansionDecision(
    target_query="dentist Krakow",
    strategy="city",
    axis_value="Krakow",
)


# ---------------------------------------------------------------------------
# search_places_activity (unchanged delegation — still calls pipeline.search_places)
# ---------------------------------------------------------------------------


async def test_search_places_returns_place_list(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    mock = AsyncMock(return_value=[_RESULT])
    monkeypatch.setattr(act, "search_places", mock)

    result = await env.run(search_places_activity, "dental Warsaw", 5)

    assert result == [_RESULT]
    mock.assert_called_once_with("dental Warsaw", 5, None)


async def test_search_places_passes_limit_to_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    mock = AsyncMock(return_value=[_RESULT, _RESULT])
    monkeypatch.setattr(act, "search_places", mock)

    await env.run(search_places_activity, "dentist", 10)

    mock.assert_called_once_with("dentist", 10, None)


async def test_search_places_propagates_mcp_error(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    monkeypatch.setattr(
        act, "search_places", AsyncMock(side_effect=RuntimeError("MCP server down"))
    )

    with pytest.raises(RuntimeError, match="MCP server down"):
        await env.run(search_places_activity, "q", 1)


# ---------------------------------------------------------------------------
# qualify_lead_activity — delegates to qualify_node
# ---------------------------------------------------------------------------


async def test_qualify_lead_returns_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()

    def _mock_node(state: LeadProcessingState, **_: object) -> dict[str, Any]:
        return {"verdict": _VERDICT}

    monkeypatch.setattr(act, "qualify_node", _mock_node)

    result = await env.run(qualify_lead_activity, "B2B dental software", _PLACE)

    assert result == _VERDICT
    assert result.is_qualified is True


async def test_qualify_lead_passes_outreach_goal(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    captured: dict[str, Any] = {}

    def _capture_node(state: LeadProcessingState, **_: object) -> dict[str, Any]:
        captured["goal"] = state["outreach_goal"]
        captured["place"] = state["place"]
        return {"verdict": _VERDICT}

    monkeypatch.setattr(act, "qualify_node", _capture_node)

    await env.run(qualify_lead_activity, "plumbing SaaS", _PLACE)

    assert captured["goal"] == "plumbing SaaS"
    assert captured["place"] == _PLACE


async def test_qualify_lead_propagates_validation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ValidationError propagates so Temporal marks the attempt non-retryable."""
    from pydantic import ValidationError

    env = ActivityEnvironment()

    def _bad_node(state: LeadProcessingState, **_: object) -> dict[str, Any]:
        # qualify_node re-raises ValidationError (doesn't catch it)
        QualifierVerdict.model_validate({"is_qualified": "yes", "score": 99})
        return {}  # unreachable

    monkeypatch.setattr(act, "qualify_node", _bad_node)

    with pytest.raises(ValidationError):
        await env.run(qualify_lead_activity, "goal", _PLACE)


async def test_qualify_lead_propagates_rate_limit_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM errors (caught by qualify_node as {"error": ...}) are re-raised by the activity."""
    env = ActivityEnvironment()

    def _error_node(state: LeadProcessingState, **_: object) -> dict[str, Any]:
        return {"error": "rate limit exceeded"}

    monkeypatch.setattr(act, "qualify_node", _error_node)

    with pytest.raises(RuntimeError, match="rate limit"):
        await env.run(qualify_lead_activity, "goal", _PLACE)


# ---------------------------------------------------------------------------
# expand_search_query_activity — delegates to dspy_engine.expand_search_query
# ---------------------------------------------------------------------------


async def test_expand_search_query_returns_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    mock = Mock(return_value=_EXPANSION_DECISION)
    monkeypatch.setattr(act, "expand_search_query", mock)

    result = await env.run(
        expand_search_query_activity,
        "B2B dental software",
        "dentist Warsaw",
        ["Warsaw"],
        [],
        5,
    )

    assert result == _EXPANSION_DECISION
    args, kwargs = mock.call_args
    assert args == ("B2B dental software", "dentist Warsaw", ["Warsaw"], [], 5)
    assert "lm" in kwargs


async def test_expand_search_query_passes_tried_axes(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    captured: dict[str, Any] = {}

    def _capture(
        prompt: str,
        target_query: str,
        tried_cities: list[str],
        tried_industries: list[str],
        still_missing: int,
        *,
        lm: Any,
    ) -> ExpansionDecision:
        captured["tried_cities"] = tried_cities
        captured["tried_industries"] = tried_industries
        captured["still_missing"] = still_missing
        return _EXPANSION_DECISION

    monkeypatch.setattr(act, "expand_search_query", _capture)

    await env.run(
        expand_search_query_activity,
        "goal",
        "dentist Warsaw",
        ["Warsaw", "Krakow"],
        ["orthodontist"],
        3,
    )

    assert captured["tried_cities"] == ["Warsaw", "Krakow"]
    assert captured["tried_industries"] == ["orthodontist"]
    assert captured["still_missing"] == 3


async def test_expand_search_query_propagates_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    monkeypatch.setattr(
        act, "expand_search_query", Mock(side_effect=RuntimeError("LLM unavailable"))
    )

    with pytest.raises(RuntimeError, match="LLM unavailable"):
        await env.run(expand_search_query_activity, "goal", "dentist Warsaw", [], [], 5)


# ---------------------------------------------------------------------------
# generate_email_activity — delegates to email_node
# ---------------------------------------------------------------------------


async def test_generate_email_returns_email(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()

    def _mock_node(state: LeadProcessingState, **_: object) -> dict[str, Any]:
        return {"email": _EMAIL}

    monkeypatch.setattr(act, "email_node", _mock_node)

    result = await env.run(
        generate_email_activity, "B2B dental software", _PLACE, _VERDICT, "I run SaaS."
    )

    assert result == _EMAIL
    assert len(result.personalization_hooks) > 0


async def test_generate_email_passes_sender_context(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()
    captured: dict[str, Any] = {}

    def _capture_node(state: LeadProcessingState, **_: object) -> dict[str, Any]:
        captured["sender_context"] = state["sender_context"]
        captured["qualifier_reasoning"] = state["verdict"].reasoning  # type: ignore[union-attr]
        return {"email": _EMAIL}

    monkeypatch.setattr(act, "email_node", _capture_node)

    await env.run(generate_email_activity, "goal", _PLACE, _VERDICT, "Sender: Jane, value prop: X")

    assert captured["sender_context"] == "Sender: Jane, value prop: X"
    assert captured["qualifier_reasoning"] == _VERDICT.reasoning


async def test_generate_email_propagates_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    env = ActivityEnvironment()

    def _error_node(state: LeadProcessingState, **_: object) -> dict[str, Any]:
        return {"error": "LLM unavailable"}

    monkeypatch.setattr(act, "email_node", _error_node)

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
    assert act.QUALIFY_TIMEOUT.total_seconds() == 90
    assert act.EXPAND_QUERY_TIMEOUT.total_seconds() == 60
    assert act.EMAIL_TIMEOUT.total_seconds() == 120


def test_retry_policies_have_non_retryable_validation_error() -> None:
    for policy in (act.SEARCH_RETRY, act.QUALIFY_RETRY, act.EXPAND_QUERY_RETRY, act.EMAIL_RETRY):
        assert policy.non_retryable_error_types is not None
        assert "ValidationError" in policy.non_retryable_error_types
