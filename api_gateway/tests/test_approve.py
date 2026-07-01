"""Tests for POST /api/leads/approve.

DB session is mocked — no live Postgres required. Temporal not used by this endpoint.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.db import RunRow, get_session
from api_gateway.main import app
from shared.schemas import GeneratedEmail, Lead, PlaceDetails

# ── Helpers ────────────────────────────────────────────────────────────────────

_leads_ta: TypeAdapter[list[Lead]] = TypeAdapter(list[Lead])

_RUN_ID = "run-id-approve-tests"


def _make_place(idx: int) -> PlaceDetails:
    return PlaceDetails(
        id=f"place-{idx:03d}",
        name=f"Business {idx}",
        address=f"{idx} Main St",
        lat=52.0,
        lng=21.0,
        category="dental",
        rating=4.5,
        review_count=100,
    )


def _make_email(idx: int) -> GeneratedEmail:
    return GeneratedEmail(
        subject=f"Subject {idx}",
        body=f"Body {idx}",
        personalization_hooks=["hook"],
        model_used="mock/test",
    )


def _make_leads(n: int, *, with_email: bool = True) -> list[Lead]:
    return [
        Lead(place=_make_place(i), email=_make_email(i) if with_email else None) for i in range(n)
    ]


def _leads_json(leads: list[Lead]) -> str:
    return json.dumps([json.loads(lead.model_dump_json()) for lead in leads])


def _make_row(leads: list[Lead]) -> RunRow:
    return RunRow(
        id=_RUN_ID,
        prompt="test",
        target_query="test",
        limit=20,
        leads_json=_leads_json(leads),
    )


# ── Fixtures ───────────────────────────────────────────────────────────────────


def _make_http(mock_session: AsyncMock) -> AsyncClient:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    app.dependency_overrides[get_session] = _session_override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ── Tests ──────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_bulk_approve_20_leads() -> None:
    """Bulk approve 20 leads in one call → updated=20, all have decision=approved."""
    leads = _make_leads(20)
    row = _make_row(leads)
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=row)
    session.commit = AsyncMock()

    async with _make_http(session) as client:
        resp = await client.post(
            "/api/leads/approve",
            json={
                "run_id": _RUN_ID,
                "lead_ids": [f"place-{i:03d}" for i in range(20)],
                "action": "approved",
            },
        )

    assert resp.status_code == 200
    assert resp.json() == {"updated": 20}
    session.commit.assert_called_once()

    # Verify all leads in DB now have decision=approved and decided_at set
    assert row.leads_json
    saved_leads = _leads_ta.validate_json(row.leads_json)
    assert all(lead.decision == "approved" for lead in saved_leads)
    assert all(lead.decided_at is not None for lead in saved_leads)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_inline_edit_applied() -> None:
    """Edited subject/body is applied before marking the lead approved."""
    leads = _make_leads(1)
    row = _make_row(leads)
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=row)

    async with _make_http(session) as client:
        resp = await client.post(
            "/api/leads/approve",
            json={
                "run_id": _RUN_ID,
                "lead_ids": ["place-000"],
                "action": "approved",
                "edited_emails": {
                    "place-000": {"subject": "Edited Subject", "body": "Edited Body"}
                },
            },
        )

    assert resp.status_code == 200
    assert resp.json()["updated"] == 1

    assert row.leads_json
    saved_leads = _leads_ta.validate_json(row.leads_json)
    email = saved_leads[0].email
    assert email is not None
    assert email.subject == "Edited Subject"
    assert email.body == "Edited Body"
    # Original metadata preserved
    assert email.personalization_hooks == ["hook"]
    assert email.model_used == "mock/test"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_lead_ids_over_50_returns_422() -> None:
    """lead_ids with 51 entries fails Pydantic validation → 422."""
    session = AsyncMock(spec=AsyncSession)

    async with _make_http(session) as client:
        resp = await client.post(
            "/api/leads/approve",
            json={
                "run_id": _RUN_ID,
                "lead_ids": [f"place-{i:03d}" for i in range(51)],
                "action": "approved",
            },
        )

    assert resp.status_code == 422

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_run_not_found_returns_404() -> None:
    """Unknown run_id → 404 Not Found."""
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=None)

    async with _make_http(session) as client:
        resp = await client.post(
            "/api/leads/approve",
            json={
                "run_id": "nonexistent-run",
                "lead_ids": ["place-000"],
                "action": "approved",
            },
        )

    assert resp.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_bulk_reject_leads() -> None:
    """Reject 5 leads out of 10 — only targeted leads are updated."""
    leads = _make_leads(10)
    row = _make_row(leads)
    session = AsyncMock(spec=AsyncSession)
    session.get = AsyncMock(return_value=row)

    async with _make_http(session) as client:
        resp = await client.post(
            "/api/leads/approve",
            json={
                "run_id": _RUN_ID,
                "lead_ids": [f"place-{i:03d}" for i in range(5)],
                "action": "rejected",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["updated"] == 5

    assert row.leads_json
    saved_leads = _leads_ta.validate_json(row.leads_json)
    rejected = [lead for lead in saved_leads if lead.decision == "rejected"]
    pending = [lead for lead in saved_leads if lead.decision == "pending"]
    assert len(rejected) == 5
    assert len(pending) == 5

    app.dependency_overrides.clear()
