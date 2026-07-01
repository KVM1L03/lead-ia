"""Tests for POST /api/leads/search.

Temporal client, DB session, and DSPy translation are all mocked so tests
run without a live Temporal server, Postgres, or Anthropic API key.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.db import get_session
from api_gateway.main import app
from api_gateway.temporal import get_temporal_client

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_temporal() -> AsyncMock:
    client = AsyncMock()
    handle = MagicMock()
    handle.id = "fixed-run-id"
    client.start_workflow = AsyncMock(return_value=handle)
    return client


@pytest.fixture
async def http(
    mock_session: AsyncMock,
    mock_temporal: AsyncMock,
) -> AsyncGenerator[AsyncClient, None]:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    app.dependency_overrides[get_session] = _session_override
    app.dependency_overrides[get_temporal_client] = lambda: mock_temporal

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_returns_workflow_id(
    http: AsyncClient,
    mock_temporal: AsyncMock,
    mock_session: AsyncMock,
) -> None:
    with patch(
        "api_gateway.routes.leads.translate_prompt",
        return_value="dental clinic Warsaw",
    ):
        resp = await http.post(
            "/api/leads/search",
            json={
                "prompt": "dental clinics warsaw",
                "limit": 20,
                "sender_context": "I sell scheduling software",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "workflow_id" in data
    assert "run_id" in data
    assert data["workflow_id"] == data["run_id"]
    # UUID-shaped
    assert len(data["run_id"]) == 36
    # Temporal and DB were called
    mock_temporal.start_workflow.assert_called_once()
    mock_session.add.assert_called_once()
    mock_session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_limit_above_200_returns_422(http: AsyncClient) -> None:
    resp = await http.post(
        "/api/leads/search",
        json={"prompt": "dentists", "limit": 201, "sender_context": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_limit_below_10_returns_422(http: AsyncClient) -> None:
    resp = await http.post(
        "/api/leads/search",
        json={"prompt": "dentists", "limit": 5, "sender_context": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_empty_prompt_returns_422(http: AsyncClient) -> None:
    resp = await http.post(
        "/api/leads/search",
        json={"prompt": "", "limit": 20, "sender_context": ""},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_temporal_receives_correct_input(
    http: AsyncClient,
    mock_temporal: AsyncMock,
) -> None:
    """Verify the workflow is started with the translated query, not the raw prompt."""
    with patch(
        "api_gateway.routes.leads.translate_prompt",
        return_value="dental clinic Warsaw",
    ):
        await http.post(
            "/api/leads/search",
            json={
                "prompt": "dental clinics warsaw",
                "limit": 50,
                "sender_context": "I run a SaaS",
            },
        )

    call_kwargs = mock_temporal.start_workflow.call_args
    lead_gen_input = call_kwargs.args[1]  # second positional arg is LeadGenInput
    assert lead_gen_input.target_query == "dental clinic Warsaw"
    assert lead_gen_input.limit == 50


@pytest.mark.asyncio
async def test_temporal_failure_marks_run_failed_and_returns_503(
    http: AsyncClient,
    mock_temporal: AsyncMock,
    mock_session: AsyncMock,
) -> None:
    """If start_workflow raises, the Run row is marked 'failed' and the
    caller receives 503 — not a stale 'scraping' row that blocks polling."""
    mock_temporal.start_workflow.side_effect = RuntimeError("Temporal unavailable")

    with patch(
        "api_gateway.routes.leads.translate_prompt",
        return_value="dental clinic Warsaw",
    ):
        resp = await http.post(
            "/api/leads/search",
            json={"prompt": "dental clinics warsaw", "limit": 20, "sender_context": ""},
        )

    assert resp.status_code == 503
    # DB row was added, then its status was updated to 'failed'
    mock_session.add.assert_called_once()
    assert mock_session.commit.await_count == 2  # first commit (insert) + second (update)
    added_row = mock_session.add.call_args.args[0]
    assert added_row.status == "failed"
