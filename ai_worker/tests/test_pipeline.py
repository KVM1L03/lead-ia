"""Tests for ai_worker/pipeline.py — shared core logic.

Invariant: both the Temporal activities and the sync path call the same
pipeline functions. This is verified by mocking at the pipeline level.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from shared.schemas import GeneratedEmail, PlaceDetails, PlaceSearchResult, QualifierVerdict

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


@pytest.mark.asyncio
async def test_run_pipeline_returns_leads() -> None:
    """run_pipeline calls search_places, get_place_details, qualify_lead_async,
    and generate_email_async — and returns a list of Lead objects."""
    with (
        patch("ai_worker.pipeline.search_places", new=AsyncMock(return_value=[_PLACE_SEARCH])),
        patch("ai_worker.pipeline.get_place_details", new=AsyncMock(return_value=_PLACE_DETAILS)),
        patch("ai_worker.pipeline.qualify_lead_async", new=AsyncMock(return_value=_VERDICT_YES)),
        patch("ai_worker.pipeline.generate_email_async", new=AsyncMock(return_value=_EMAIL)),
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
        patch("ai_worker.pipeline.qualify_lead_async", new=AsyncMock(return_value=_VERDICT_NO)),
        patch("ai_worker.pipeline.generate_email_async", new=AsyncMock(return_value=_EMAIL)),
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
    assert leads[0].email is None  # not generated for unqualified leads


@pytest.mark.asyncio
async def test_run_pipeline_qualify_error_produces_lead_with_error() -> None:
    """When qualify_lead_async raises, the lead is included with an error field."""
    with (
        patch("ai_worker.pipeline.search_places", new=AsyncMock(return_value=[_PLACE_SEARCH])),
        patch("ai_worker.pipeline.get_place_details", new=AsyncMock(return_value=_PLACE_DETAILS)),
        patch(
            "ai_worker.pipeline.qualify_lead_async",
            new=AsyncMock(side_effect=RuntimeError("LLM timeout")),
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
    assert leads[0].error == "LLM timeout"
    assert leads[0].verdict is None
    assert leads[0].email is None


@pytest.mark.asyncio
async def test_search_places_activity_calls_pipeline_search_places() -> None:
    """The Temporal activity is a thin wrapper — it calls pipeline.search_places."""
    with patch(
        "ai_worker.activities.search_places", new=AsyncMock(return_value=[])
    ) as mock_sp:
        from temporalio.testing import ActivityEnvironment

        from ai_worker.activities import search_places_activity

        env = ActivityEnvironment()
        await env.run(search_places_activity, "dental clinic", 10)

    mock_sp.assert_called_once_with("dental clinic", 10)


@pytest.mark.asyncio
async def test_qualify_lead_activity_calls_pipeline_qualify_lead_async() -> None:
    """qualify_lead_activity delegates to pipeline.qualify_lead_async."""
    with patch(
        "ai_worker.activities.qualify_lead_async",
        new=AsyncMock(return_value=_VERDICT_YES),
    ) as mock_q:
        from temporalio.testing import ActivityEnvironment

        from ai_worker.activities import qualify_lead_activity

        env = ActivityEnvironment()
        result = await env.run(qualify_lead_activity, "find dentists", _PLACE_DETAILS)

    mock_q.assert_called_once_with("find dentists", _PLACE_DETAILS)
    assert result.is_qualified is True


@pytest.mark.asyncio
async def test_generate_email_activity_calls_pipeline_generate_email_async() -> None:
    """generate_email_activity delegates to pipeline.generate_email_async."""
    with patch(
        "ai_worker.activities.generate_email_async",
        new=AsyncMock(return_value=_EMAIL),
    ) as mock_e:
        from temporalio.testing import ActivityEnvironment

        from ai_worker.activities import generate_email_activity

        env = ActivityEnvironment()
        result = await env.run(
            generate_email_activity, "find dentists", _PLACE_DETAILS, _VERDICT_YES, "I sell SaaS"
        )

    mock_e.assert_called_once_with("find dentists", _PLACE_DETAILS, _VERDICT_YES, "I sell SaaS")
    assert result.subject == "Hi"
