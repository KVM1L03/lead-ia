"""POST /api/leads/search — trigger a LeadGenerationWorkflow run or run inline.

Two execution modes (controlled by EXECUTION_MODE env var):

  temporal (default):
    1. Translate user prompt → Google Maps search query (DSPy, Haiku).
    2. Persist a Run row with status='scraping'.
    3. Start LeadGenerationWorkflow on Temporal (fire-and-forget).
    4. Return {workflow_id, run_id, mode="temporal", results=[]}.
    The caller polls /api/leads/status/{id}; this endpoint returns immediately.

  sync (demo/Cloud Run):
    1. Translate user prompt.
    2. Run the full pipeline inline via asyncio.gather fan-out.
    3. Skip DB write when PERSISTENCE_ENABLED=false.
    4. Return {workflow_id, run_id, mode="sync", results=[...leads]}.
    The caller renders results immediately — no polling needed.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Literal

import dspy
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from api_gateway.config import settings
from api_gateway.db import RunRow, get_session_maybe
from api_gateway.rate_limit import enforce_run_limit
from api_gateway.temporal import get_temporal_client_maybe
from shared.schemas import Lead

router = APIRouter(prefix="/api/leads")

# ── DSPy PromptToQuery ────────────────────────────────────────────────────────

_TASK_QUEUE = "leads"


class PromptToQuery(dspy.Signature):  # type: ignore[misc]
    """Convert a natural-language outreach description into a Google Maps search query."""

    prompt: str = dspy.InputField(
        desc="User's natural-language description of what leads they want, "
        "e.g. 'dental clinics in Warsaw that might need scheduling software'"
    )
    target_query: str = dspy.OutputField(
        desc="A concise, Google Maps search-friendly query, "
        "e.g. 'dental clinic Warsaw'. "
        "No quotes, no extra explanation — just the search terms."
    )


_prompt_to_query = dspy.Predict(PromptToQuery)

_lm: dspy.LM | None = None


def _get_lm() -> dspy.LM:
    global _lm
    if _lm is None:
        _lm = dspy.LM("anthropic/claude-haiku-4-5-20251001")
    return _lm


def translate_prompt(prompt: str) -> str:
    """Run PromptToQuery and return the search query string."""
    with dspy.context(lm=_get_lm()):
        result = _prompt_to_query(prompt=prompt)
    return str(result.target_query).strip()


def _effective_maps_provider(
    requested: Literal["mock", "serpapi", "google_places"] | None,
) -> Literal["mock", "serpapi", "google_places"] | None:
    """Return the maps provider for this request.

    Public demo deployments force mock so stale browser localStorage cannot
    trigger billable SerpAPI / Google Places calls without configured keys.
    """
    if settings.DEMO_MODE:
        return "mock"
    return requested


# ── Request / Response schemas ────────────────────────────────────────────────


class SearchRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    prompt: Annotated[str, Field(min_length=1, max_length=500)]
    limit: Annotated[int, Field(ge=10, le=200)] = 20
    sender_context: Annotated[str, Field(max_length=1000)] = ""
    maps_provider: Literal["mock", "serpapi", "google_places"] | None = None


class SearchResponse(BaseModel):
    workflow_id: str
    run_id: str
    mode: Literal["temporal", "sync"] = "temporal"
    results: list[Lead] = []


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/search", response_model=SearchResponse)
async def search_leads(
    body: SearchRequest,
    _: Annotated[None, Depends(enforce_run_limit)],  # Layer 1: global daily cap
    session: Annotated[AsyncSession | None, Depends(get_session_maybe)],
    temporal: Annotated[Client | None, Depends(get_temporal_client_maybe)],
) -> SearchResponse:
    """Kick off a lead-generation workflow or run inline (depending on EXECUTION_MODE)."""
    run_id = str(uuid.uuid4())
    target_query = await asyncio.to_thread(translate_prompt, body.prompt)
    maps_provider = _effective_maps_provider(body.maps_provider)

    if settings.EXECUTION_MODE == "sync":
        from ai_worker.pipeline import run_pipeline

        effective_limit = min(body.limit, settings.DEMO_MAX_LEADS_SYNC)
        leads = await run_pipeline(
            prompt=body.prompt,
            target_query=target_query,
            limit=effective_limit,
            sender_context=body.sender_context,
            maps_provider=maps_provider,
        )
        return SearchResponse(workflow_id=run_id, run_id=run_id, mode="sync", results=leads)

    # ── Temporal path ──────────────────────────────────────────────────────────
    from ai_worker.workflows import LeadGenerationWorkflow, LeadGenInput

    if session is not None:
        row = RunRow(
            id=run_id,
            prompt=body.prompt,
            target_query=target_query,
            limit=body.limit,
            sender_context=body.sender_context,
            status="scraping",
        )
        session.add(row)
        await session.commit()

    if temporal is None:
        if session is not None:
            row.status = "failed"
            await session.commit()
        raise HTTPException(status_code=503, detail="Workflow service unavailable")

    try:
        await temporal.start_workflow(
            LeadGenerationWorkflow.run,
            LeadGenInput(
                prompt=body.prompt,
                target_query=target_query,
                limit=body.limit,
                sender_context=body.sender_context,
                maps_provider=maps_provider,
            ),
            id=run_id,
            task_queue=_TASK_QUEUE,
        )
    except Exception as exc:
        if session is not None:
            row.status = "failed"
            await session.commit()
        raise HTTPException(status_code=503, detail="Workflow service unavailable") from exc

    return SearchResponse(workflow_id=run_id, run_id=run_id, mode="temporal")
