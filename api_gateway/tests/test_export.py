"""Tests for leads_to_csv serialization and POST /api/leads/export endpoint."""

from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.db import RunRow, get_session_maybe
from api_gateway.main import app
from api_gateway.routes.export import COLUMNS, leads_to_csv
from shared.schemas import GeneratedEmail, Lead, PlaceDetails, QualifierVerdict

# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_place(idx: int = 1, *, name: str | None = None) -> PlaceDetails:
    return PlaceDetails(
        id=f"place-{idx:03d}",
        name=name or f"Stomatologia Łódź {idx}",  # Polish chars: UTF-8 smoke test
        address=f"ul. Piotrkowska {idx}, Łódź",
        lat=51.77,
        lng=19.45,
        category="dental",
        rating=4.7,
        review_count=214,
        website="https://stom.pl",
        phone="+48 42 123 456",
    )


def _make_verdict() -> QualifierVerdict:
    return QualifierVerdict(
        is_qualified=True,
        score=0.9,
        reasoning="Strong ICP fit for dental software.",
        icp_fit={"is_b2b": True, "has_website": True},
    )


def _make_email(body: str = "Hi — we help dental clinics.") -> GeneratedEmail:
    return GeneratedEmail(
        subject="Quick question from us",
        body=body,
        personalization_hooks=["4.7 stars", "Łódź location"],
        model_used="mock/test",
    )


def _make_approved_lead(idx: int = 1, *, email_body: str | None = None) -> Lead:
    return Lead(
        place=_make_place(idx),
        verdict=_make_verdict(),
        email=_make_email(email_body or "Hi — we help dental clinics."),
        decision="approved",
    )


def _leads_json(leads: list[Lead]) -> str:
    return json.dumps([json.loads(lead.model_dump_json()) for lead in leads])


# ── Pure-function tests ───────────────────────────────────────────────────────


def test_columns_and_order() -> None:
    """All 12 columns present in exact spec order; values map correctly."""
    lead = _make_approved_lead()
    result = leads_to_csv([lead])
    reader = csv.DictReader(io.StringIO(result))
    rows = list(reader)
    assert len(rows) == 1
    assert list(rows[0].keys()) == COLUMNS
    row = rows[0]
    assert row["business_name"] == "Stomatologia Łódź 1"
    assert row["address"] == "ul. Piotrkowska 1, Łódź"
    assert row["website"] == "https://stom.pl"
    assert row["phone"] == "+48 42 123 456"
    assert row["category"] == "dental"
    assert row["rating"] == "4.7"
    assert row["review_count"] == "214"
    assert row["qualifier_score"] == "0.9"
    assert row["qualifier_reasoning"] == "Strong ICP fit for dental software."
    assert row["email_subject"] == "Quick question from us"
    assert row["email_body"] == "Hi — we help dental clinics."
    assert row["personalization_hooks"] == "4.7 stars; Łódź location"


def test_email_body_commas_newlines_quotes_roundtrip() -> None:
    """Email body with commas, newlines, quotes round-trips exactly through CSV."""
    nasty_body = (
        'Hi "Piotr",\n'
        "We noticed your clinic at ul. Nowy Świat, Warszawa,\n"
        "that's why \"we're\" reaching out.\n"
        "Best, LeadIA"
    )
    lead = _make_approved_lead(email_body=nasty_body)
    csv_str = leads_to_csv([lead])
    reader = csv.DictReader(io.StringIO(csv_str))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["email_body"] == nasty_body  # exact round-trip, no corruption


def test_non_approved_leads_excluded() -> None:
    """Only approved leads appear; rejected and pending are filtered out."""
    leads: list[Lead] = [
        _make_approved_lead(1),
        Lead(place=_make_place(2), decision="rejected"),
        Lead(place=_make_place(3), decision="pending"),
    ]
    result = leads_to_csv(leads)
    reader = csv.DictReader(io.StringIO(result))
    rows = list(reader)
    assert len(rows) == 1
    assert rows[0]["business_name"] == "Stomatologia Łódź 1"


def test_empty_approved_set_returns_header_only() -> None:
    """No approved leads → CSV with header row only (no data rows)."""
    leads = [Lead(place=_make_place(1), decision="rejected")]
    result = leads_to_csv(leads)
    reader = csv.DictReader(io.StringIO(result))
    assert list(reader.fieldnames or []) == COLUMNS
    assert list(reader) == []  # no data rows


def test_leads_to_csv_null_rating_and_review_count_writes_empty_cells() -> None:
    """None rating/review_count → empty CSV cell, not 'None' or crash."""
    place = PlaceDetails(
        id="p-no-rating",
        name="No Rating Biz",
        address="ul. Nowa 1, Warszawa",
        lat=52.2,
        lng=21.0,
        category="services",
        rating=None,
        review_count=None,
    )
    verdict = QualifierVerdict(is_qualified=True, score=0.8, reasoning="Fits.", icp_fit={})
    email = GeneratedEmail(subject="Hi", body="Body", personalization_hooks=[], model_used="haiku")
    lead = Lead(place=place, verdict=verdict, email=email, decision="approved")
    csv_text = leads_to_csv([lead])
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert len(rows) == 1
    assert rows[0]["rating"] == ""
    assert rows[0]["review_count"] == ""


# ── HTTP-level tests ──────────────────────────────────────────────────────────


def _db_client(mock_session: AsyncMock) -> AsyncClient:
    async def _session_override() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    app.dependency_overrides[get_session_maybe] = _session_override
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _sync_client() -> AsyncClient:
    async def _no_session() -> AsyncGenerator[None, None]:
        yield None

    app.dependency_overrides[get_session_maybe] = _no_session
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_both_modes_produce_identical_csv() -> None:
    """DB mode and sync mode return identical CSV bytes for the same leads."""
    leads = [_make_approved_lead()]
    run_id = "run-export-test-001"
    row = RunRow(
        id=run_id,
        prompt="test",
        target_query="dentist Warsaw",
        limit=10,
        leads_json=_leads_json(leads),
    )
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get = AsyncMock(return_value=row)

    async with _db_client(mock_session) as client:
        db_resp = await client.post("/api/leads/export", json={"run_id": run_id})

    async with _sync_client() as client:
        sync_resp = await client.post(
            "/api/leads/export",
            json={"leads": [json.loads(lead.model_dump_json()) for lead in leads]},
        )

    app.dependency_overrides.clear()

    assert db_resp.status_code == 200
    assert sync_resp.status_code == 200
    # CSV content must be byte-for-byte identical regardless of mode
    assert db_resp.text == sync_resp.text


@pytest.mark.asyncio
async def test_response_headers() -> None:
    """Response has correct Content-Type and Content-Disposition."""
    leads = [_make_approved_lead()]

    async with _sync_client() as client:
        resp = await client.post(
            "/api/leads/export",
            json={"leads": [json.loads(lead.model_dump_json()) for lead in leads]},
        )

    app.dependency_overrides.clear()

    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "utf-8" in resp.headers["content-type"]
    cd = resp.headers["content-disposition"]
    assert cd.startswith('attachment; filename="leadia-export-')
    assert cd.endswith('.csv"')


@pytest.mark.asyncio
async def test_db_mode_run_not_found_returns_404() -> None:
    """Unknown run_id in DB mode → 404."""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.get = AsyncMock(return_value=None)

    async with _db_client(mock_session) as client:
        resp = await client.post("/api/leads/export", json={"run_id": "nonexistent"})

    app.dependency_overrides.clear()
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sync_mode_missing_leads_returns_422() -> None:
    """Sync mode with no leads in body → 422."""
    async with _sync_client() as client:
        resp = await client.post("/api/leads/export", json={"run_id": None})

    app.dependency_overrides.clear()
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_db_mode_missing_run_id_returns_422() -> None:
    """DB mode with no run_id in body → 422."""
    mock_session = AsyncMock(spec=AsyncSession)

    async with _db_client(mock_session) as client:
        resp = await client.post("/api/leads/export", json={})

    app.dependency_overrides.clear()
    assert resp.status_code == 422
