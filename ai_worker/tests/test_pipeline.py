"""Tests for ai_worker/pipeline.py — shared core logic.

Invariant: both the Temporal activities and the sync path call the same
graph nodes. This is verified by mocking at the graph entry point.

Error model for process_one_lead:
  - LLM/network errors: caught inside qualify_node/email_node → process_one_lead
    returns Lead(error=...) — never raises for these.
  - ValidationError: re-raised by nodes → process_one_lead raises → _process
    wrapper catches it → Lead(error=...) returned from run_pipeline.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from shared.schemas import GeneratedEmail, Lead, PlaceDetails, PlaceSearchResult, QualifierVerdict

_PLACE_SEARCH = PlaceSearchResult(
    id="p1",
    name="Acme Dental",
    address="Warsaw 1",
    lat=52.0,
    lng=21.0,
    category="dentist",
    rating=4.5,
    review_count=100,
)
_PLACE_DETAILS = PlaceDetails(
    id="p1",
    name="Acme Dental",
    address="Warsaw 1",
    lat=52.0,
    lng=21.0,
    category="dentist",
    rating=4.5,
    review_count=100,
    website="https://acme.pl",
)
_VERDICT_YES = QualifierVerdict(
    is_qualified=True, score=0.9, reasoning="good fit", icp_fit={"ok": True}
)
_VERDICT_NO = QualifierVerdict(
    is_qualified=False, score=0.1, reasoning="bad fit", icp_fit={"ok": False}
)
_EMAIL = GeneratedEmail(
    subject="Hi",
    body="Hello there",
    personalization_hooks=["4.5-star rating"],
    model_used="haiku",
)

_LEAD_YES = Lead(place=_PLACE_DETAILS, verdict=_VERDICT_YES, email=_EMAIL)
_LEAD_NO = Lead(place=_PLACE_DETAILS, verdict=_VERDICT_NO)
_LEAD_ERROR = Lead(place=_PLACE_DETAILS, error="LLM timeout")


@pytest.mark.asyncio
async def test_run_pipeline_returns_leads() -> None:
    """run_pipeline calls search_places, get_place_details, process_one_lead, returns Leads."""
    with (
        patch("ai_worker.pipeline.search_places", new=AsyncMock(return_value=[_PLACE_SEARCH])),
        patch("ai_worker.pipeline.get_place_details", new=AsyncMock(return_value=_PLACE_DETAILS)),
        patch("ai_worker.pipeline.process_one_lead", return_value=_LEAD_YES),
    ):
        from ai_worker.pipeline import run_pipeline

        leads = await run_pipeline(
            prompt="find dental clinics",
            target_query="dental clinic warsaw",
            limit=10,
            sender_context="I sell SaaS",
        )

    assert len(leads) == 1
    assert leads[0].place.id == "p1"
    assert leads[0].email is not None
    assert leads[0].email.subject == "Hi"


@pytest.mark.asyncio
async def test_run_pipeline_unqualified_leads_have_no_email() -> None:
    """Leads that fail qualification are included but have no email."""
    with (
        patch("ai_worker.pipeline.search_places", new=AsyncMock(return_value=[_PLACE_SEARCH])),
        patch("ai_worker.pipeline.get_place_details", new=AsyncMock(return_value=_PLACE_DETAILS)),
        patch("ai_worker.pipeline.process_one_lead", return_value=_LEAD_NO),
    ):
        from ai_worker.pipeline import run_pipeline

        leads = await run_pipeline(
            prompt="find dental clinics",
            target_query="dental clinic warsaw",
            limit=10,
            sender_context="",
        )

    assert len(leads) == 1
    assert leads[0].verdict is not None
    assert leads[0].verdict.is_qualified is False
    assert leads[0].email is None


@pytest.mark.asyncio
async def test_run_pipeline_llm_error_produces_lead_with_error() -> None:
    """LLM errors are caught inside qualify_node → process_one_lead returns Lead(error=...).

    process_one_lead does NOT raise for LLM errors — the node absorbs them.
    """
    with (
        patch("ai_worker.pipeline.search_places", new=AsyncMock(return_value=[_PLACE_SEARCH])),
        patch("ai_worker.pipeline.get_place_details", new=AsyncMock(return_value=_PLACE_DETAILS)),
        patch("ai_worker.pipeline.process_one_lead", return_value=_LEAD_ERROR),
    ):
        from ai_worker.pipeline import run_pipeline

        leads = await run_pipeline(
            prompt="find dental clinics",
            target_query="dental clinic warsaw",
            limit=10,
            sender_context="",
        )

    assert len(leads) == 1
    assert leads[0].error == "LLM timeout"
    assert leads[0].verdict is None
    assert leads[0].email is None


@pytest.mark.asyncio
async def test_run_pipeline_process_one_lead_exception_produces_lead_with_error() -> None:
    """If process_one_lead raises (e.g. ValidationError propagated from a node),
    the _process wrapper catches it and returns Lead(error=...) so other leads continue.
    """
    with (
        patch("ai_worker.pipeline.search_places", new=AsyncMock(return_value=[_PLACE_SEARCH])),
        patch("ai_worker.pipeline.get_place_details", new=AsyncMock(return_value=_PLACE_DETAILS)),
        patch(
            "ai_worker.pipeline.process_one_lead",
            side_effect=RuntimeError("schema mismatch"),
        ),
    ):
        from ai_worker.pipeline import run_pipeline

        leads = await run_pipeline(
            prompt="find dental clinics",
            target_query="dental clinic warsaw",
            limit=10,
            sender_context="",
        )

    assert len(leads) == 1
    assert leads[0].error == "schema mismatch"
    assert leads[0].verdict is None
    assert leads[0].email is None


@pytest.mark.asyncio
async def test_search_places_activity_calls_pipeline_search_places() -> None:
    """The Temporal activity is a thin wrapper — it calls pipeline.search_places."""
    with patch("ai_worker.activities.search_places", new=AsyncMock(return_value=[])) as mock_sp:
        from temporalio.testing import ActivityEnvironment

        from ai_worker.activities import search_places_activity

        env = ActivityEnvironment()
        await env.run(search_places_activity, "dental clinic", 10)

    mock_sp.assert_called_once_with("dental clinic", 10)


@pytest.mark.asyncio
async def test_qualify_lead_activity_calls_graph_qualify_node() -> None:
    """qualify_lead_activity delegates to qualify_node (graph node), not pipeline directly."""
    captured: dict = {}

    def _mock_qualify_node(state: dict) -> dict:
        captured["goal"] = state["outreach_goal"]
        captured["place"] = state["place"]
        return {"verdict": _VERDICT_YES}

    with patch("ai_worker.activities.qualify_node", _mock_qualify_node):
        from temporalio.testing import ActivityEnvironment

        from ai_worker.activities import qualify_lead_activity

        env = ActivityEnvironment()
        result = await env.run(qualify_lead_activity, "find dentists", _PLACE_DETAILS)

    assert captured["goal"] == "find dentists"
    assert captured["place"] == _PLACE_DETAILS
    assert result.is_qualified is True


@pytest.mark.asyncio
async def test_generate_email_activity_calls_graph_email_node() -> None:
    """generate_email_activity delegates to email_node (graph node), not pipeline directly."""
    captured: dict = {}

    def _mock_email_node(state: dict) -> dict:
        captured["sender_context"] = state["sender_context"]
        return {"email": _EMAIL}

    with patch("ai_worker.activities.email_node", _mock_email_node):
        from temporalio.testing import ActivityEnvironment

        from ai_worker.activities import generate_email_activity

        env = ActivityEnvironment()
        result = await env.run(
            generate_email_activity, "find dentists", _PLACE_DETAILS, _VERDICT_YES, "I sell SaaS"
        )

    assert captured["sender_context"] == "I sell SaaS"
    assert result.subject == "Hi"
