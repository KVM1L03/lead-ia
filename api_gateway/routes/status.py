"""GET /api/leads/status/{workflow_id} — poll a running lead-gen workflow.

Design:
  - Stage + counts come from a Temporal in-memory query (fast, always current).
  - Leads list comes from the DB (written by persist_phase_result_activity at
    each phase boundary; never from workflow state directly per constraints).
  - If the DB row is absent the run never started → 404.
  - If Temporal is unreachable, stage/counts fall back to last DB snapshot.

Response shape:
  {
    "status": "scraping" | "qualifying" | "generating" | "completed" | "failed",
    "progress": {"scraped": int, "qualified": int, "emails_generated": int},
    "results": list[Lead]   // grows as phases complete
  }
"""

from __future__ import annotations

from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from api_gateway.db import RunRow, get_session
from api_gateway.temporal import get_temporal_client
from shared.schemas import Lead

_leads_ta: TypeAdapter[list[Lead]] = TypeAdapter(list[Lead])

router = APIRouter(prefix="/api/leads")

# Temporal internal stages → public API status
_STAGE_MAP: dict[str, str] = {
    "scraping": "scraping",
    "getting_details": "scraping",
    "qualifying": "qualifying",
    "generating": "generating",
    "completed": "completed",
    "failed": "failed",
}


# ── Response models ───────────────────────────────────────────────────────────


class ProgressCounts(BaseModel):
    model_config = ConfigDict(strict=True)

    scraped: int
    qualified: int
    emails_generated: int


class StatusResponse(BaseModel):
    status: Literal["scraping", "qualifying", "generating", "completed", "failed"]
    progress: ProgressCounts
    results: list[Lead]


# ── Route ─────────────────────────────────────────────────────────────────────


@router.get("/status/{workflow_id}", response_model=StatusResponse)
async def get_status(
    workflow_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    temporal: Annotated[Client, Depends(get_temporal_client)],
) -> StatusResponse:
    """Return the current status, progress counts, and partial results for a run."""
    from ai_worker.workflows import LeadGenerationWorkflow, WorkflowProgress

    # 1. DB row must exist — if absent, the run_id is unknown ──────────────────
    row: RunRow | None = await session.get(RunRow, workflow_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # 2. Query Temporal for real-time stage + counts (fast in-memory query) ─────
    stage = row.status
    scraped = row.scraped
    qualified = row.qualified
    emails_generated = row.emails_generated

    handle = temporal.get_workflow_handle(workflow_id)
    try:
        progress: WorkflowProgress = await handle.query(LeadGenerationWorkflow.get_progress)
        stage = _STAGE_MAP.get(progress.stage, progress.stage)
        scraped = progress.total
        qualified = progress.qualified
        emails_generated = progress.emailed
    except Exception:
        # Temporal unreachable or workflow history evicted → use DB snapshot
        stage = _STAGE_MAP.get(row.status, row.status)

    # 3. Leads from DB (populated by persist_phase_result_activity) ─────────────
    leads: list[Lead] = []
    if row.leads_json:
        leads = _leads_ta.validate_json(row.leads_json)

    return StatusResponse(
        status=cast(Literal["scraping", "qualifying", "generating", "completed", "failed"], stage),
        progress=ProgressCounts(
            scraped=scraped,
            qualified=qualified,
            emails_generated=emails_generated,
        ),
        results=leads,
    )
