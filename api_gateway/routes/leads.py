"""POST /api/leads/search — trigger a LeadGenerationWorkflow run.

Flow:
  1. Translate user prompt → Google Maps search query (DSPy, Haiku).
  2. Persist a Run row with status='scraping'.
  3. Start LeadGenerationWorkflow on Temporal (fire-and-forget).
  4. Return {workflow_id, run_id}.

The caller polls a separate endpoint for progress; this endpoint returns
immediately — it does NOT wait for workflow completion.
"""

from __future__ import annotations

import os
import uuid
from typing import Annotated

import dspy
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from api_gateway.db import RunRow, get_session

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


# ── Temporal client (lazy, one per process) ───────────────────────────────────

_temporal_client: Client | None = None


async def get_temporal_client() -> Client:
    """FastAPI dependency — returns a shared Temporal client (lazy init)."""
    global _temporal_client
    if _temporal_client is None:
        address = os.environ.get("TEMPORAL_ADDRESS", "localhost:7233")
        _temporal_client = await Client.connect(address, data_converter=pydantic_data_converter)
    return _temporal_client


# ── Request / Response schemas ────────────────────────────────────────────────


class SearchRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    prompt: Annotated[str, Field(min_length=1, max_length=500)]
    limit: Annotated[int, Field(ge=10, le=200)] = 20
    sender_context: Annotated[str, Field(max_length=1000)] = ""


class SearchResponse(BaseModel):
    workflow_id: str
    run_id: str


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/search", response_model=SearchResponse)
async def search_leads(
    body: SearchRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    temporal: Annotated[Client, Depends(get_temporal_client)],
) -> SearchResponse:
    """Kick off a lead-generation workflow and return its ID immediately."""
    from ai_worker.workflows import LeadGenerationWorkflow, LeadGenInput

    run_id = str(uuid.uuid4())
    target_query = translate_prompt(body.prompt)

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

    try:
        await temporal.start_workflow(
            LeadGenerationWorkflow.run,
            LeadGenInput(
                prompt=body.prompt,
                target_query=target_query,
                limit=body.limit,
                sender_context=body.sender_context,
            ),
            id=run_id,
            task_queue=_TASK_QUEUE,
        )
    except Exception as exc:
        row.status = "failed"
        await session.commit()
        raise HTTPException(status_code=503, detail="Workflow service unavailable") from exc

    return SearchResponse(workflow_id=run_id, run_id=run_id)
