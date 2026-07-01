"""Tests for GET /api/leads/status/{workflow_id}.

All external dependencies (DB session, Temporal client) are mocked so tests
run without a live server or database.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.db import RunRow, get_session
from api_gateway.main import app
from api_gateway.temporal import get_temporal_client
from shared.schemas import (
    GeneratedEmail,
    Lead,
    PlaceDetails,
    QualifierVerdict,
)

# ── Shared test data ───────────────────────────────────────────────────────────

_PLACE = PlaceDetails(
    id="place-001",
    name="Klinika Centrum",
    address="ul. Nowy Swiat 28, Warszawa",
    lat=52.233,
    lng=21.021,
    category="dental",
    rating=4.8,
    review_count=187,
    website="https://klinika.pl",
    phone="+48 22 826 1234",
    hours=["Mon-Fri 8:00-20:00"],
    photos=[],
)

_VERDICT = QualifierVerdict(
    is_qualified=True,
    score=0.9,
    reasoning="Strong ICP fit.",
    icp_fit={"is_b2b": True, "has_website": True, "size_match": True},
)

_EMAIL = GeneratedEmail(
    subject="Quick question",
    body="Hi — we help dental clinics.",
    personalization_hooks=["4.8 stars"],
    model_used="mock/test",
)

_LEADS = [Lead(place=_PLACE, verdict=_VERDICT, email=_EMAIL)]

_WORKFLOW_ID = "test-run-id-1234-5678-90ab-cdef01234567"


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_row(
    *,
    status: str = "qualifying",
    scraped: int = 5,
    qualified: int = 3,
    emails_generated: int = 0,
    leads_json: str | None = None,
) -> RunRow:
    return RunRow(
        id=_WORKFLOW_ID,
        prompt="dental SaaS",
        target_query="dentist Warsaw",
        limit=20,
        sender_context="",
        status=status,
        scraped=scraped,
        qualified=qualified,
        emails_generated=emails_generated,
        leads_json=leads_json,
    )


@pytest.fixture
def mock_temporal_in_progress() -> AsyncMock:
    """Temporal returns a mid-pipeline progress query."""
    from ai_worker.workflows import WorkflowProgress

    client = AsyncMock()
    handle = AsyncMock()
    handle.query = AsyncMock(
        return_value=WorkflowProgress(stage="qualifying", total=5, qualified=0, emailed=0)
    )
    client.get_workflow_handle = MagicMock(return_value=handle)
    return client


@pytest.fixture
def mock_temporal_unreachable() -> AsyncMock:
    """Temporal query raises (server unavailable)."""
    client = AsyncMock()
    handle = AsyncMock()
    handle.query = AsyncMock(side_effect=RuntimeError("temporal down"))
    client.get_workflow_handle = MagicMock(return_value=handle)
    return client


def _make_http(mock_session: AsyncMock, mock_temporal: AsyncMock) -> AsyncClient:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_temporal_client] = lambda: mock_temporal
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_unknown_workflow_id_returns_404() -> None:
    """Row absent in DB → 404 Not Found."""
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=None)

    temporal = AsyncMock()
    temporal.get_workflow_handle = MagicMock(return_value=AsyncMock())

    async with _make_http(session, temporal) as client:
        resp = await client.get(f"/api/leads/status/{_WORKFLOW_ID}")

    assert resp.status_code == 404
    assert resp.json()["detail"] == "Run not found"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_in_progress_returns_stage_and_counts(
    mock_temporal_in_progress: AsyncMock,
) -> None:
    """In-flight workflow: stage comes from Temporal query, leads list is empty."""
    row = _make_row(status="scraping", scraped=0)
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=row)

    async with _make_http(session, mock_temporal_in_progress) as client:
        resp = await client.get(f"/api/leads/status/{_WORKFLOW_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "qualifying"
    assert data["progress"]["scraped"] == 5
    assert data["progress"]["qualified"] == 0
    assert data["results"] == []

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_completed_returns_full_leads(
    mock_temporal_in_progress: AsyncMock,
) -> None:
    """Completed workflow: leads_json in DB is deserialised and returned."""
    leads_json = json.dumps([json.loads(lead.model_dump_json()) for lead in _LEADS])
    row = _make_row(
        status="completed",
        scraped=5,
        qualified=3,
        emails_generated=3,
        leads_json=leads_json,
    )
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=row)

    # Override Temporal to return completed progress
    from ai_worker.workflows import WorkflowProgress

    handle = AsyncMock()
    handle.query = AsyncMock(
        return_value=WorkflowProgress(stage="completed", total=5, qualified=3, emailed=3)
    )
    mock_temporal_in_progress.get_workflow_handle = MagicMock(return_value=handle)

    async with _make_http(session, mock_temporal_in_progress) as client:
        resp = await client.get(f"/api/leads/status/{_WORKFLOW_ID}")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "completed"
    assert data["progress"]["emails_generated"] == 3
    assert len(data["results"]) == 1
    assert data["results"][0]["place"]["name"] == "Klinika Centrum"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_temporal_unreachable_falls_back_to_db(
    mock_temporal_unreachable: AsyncMock,
) -> None:
    """When Temporal query raises, status falls back to the DB row values."""
    row = _make_row(status="qualifying", scraped=5, qualified=2)
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=row)

    async with _make_http(session, mock_temporal_unreachable) as client:
        resp = await client.get(f"/api/leads/status/{_WORKFLOW_ID}")

    assert resp.status_code == 200
    data = resp.json()
    # Fell back to DB snapshot
    assert data["status"] == "qualifying"
    assert data["progress"]["scraped"] == 5
    assert data["progress"]["qualified"] == 2

    app.dependency_overrides.clear()
