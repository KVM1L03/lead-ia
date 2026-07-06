"""Temporal activities — thin wrappers that add retry policy constants and observability.

Per-lead business logic lives in agent_graph.py nodes. Both Temporal activities (here)
and the sync execution path (pipeline.py) delegate to the same graph nodes.
"""

import asyncio
import json
from datetime import timedelta

from temporalio import activity
from temporalio.common import RetryPolicy

from ai_worker.agent_graph import (
    LeadProcessingState,
    email_node,
    qualify_node,
)
from ai_worker.observability import activity_span
from ai_worker.pipeline import (
    get_place_details,
    search_places,
)
from shared.schemas import GeneratedEmail, Lead, PlaceDetails, PlaceSearchResult, QualifierVerdict

# ── Timeout defaults — referenced by workflows when scheduling ─────────────────
SEARCH_TIMEOUT = timedelta(seconds=60)
GET_DETAILS_TIMEOUT = timedelta(seconds=30)
QUALIFY_TIMEOUT = timedelta(seconds=90)
EMAIL_TIMEOUT = timedelta(seconds=120)
PERSIST_TIMEOUT = timedelta(seconds=30)

# ── Retry policies ─────────────────────────────────────────────────────────────
# ValidationError means bad data — retrying the same call won't help.
# Network / rate-limit errors are retryable (Temporal's default behaviour).
_NON_RETRYABLE = ["ValidationError"]

SEARCH_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    non_retryable_error_types=_NON_RETRYABLE,
)
GET_DETAILS_RETRY = RetryPolicy(
    maximum_attempts=3,
    non_retryable_error_types=_NON_RETRYABLE,
)
QUALIFY_RETRY = RetryPolicy(
    maximum_attempts=3,
    non_retryable_error_types=_NON_RETRYABLE,
)
EMAIL_RETRY = RetryPolicy(
    maximum_attempts=3,
    non_retryable_error_types=_NON_RETRYABLE,
)
PERSIST_RETRY = RetryPolicy(maximum_attempts=5, non_retryable_error_types=[])


# ── Activities ─────────────────────────────────────────────────────────────────


@activity.defn
async def search_places_activity(query: str, limit: int) -> list[PlaceSearchResult]:
    """Call maps_bridge MCP server to search Google Places."""
    info = activity.info()
    with activity_span("search_places", workflow_id=info.workflow_id or ""):
        return await search_places(query, limit)


@activity.defn
async def get_place_details_activity(place_id: str) -> PlaceDetails:
    """Fetch full place details from maps_bridge MCP server."""
    info = activity.info()
    with activity_span("get_place_details", workflow_id=info.workflow_id or "", lead_id=place_id):
        return await get_place_details(place_id)


@activity.defn
async def qualify_lead_activity(outreach_goal: str, place: PlaceDetails) -> QualifierVerdict:
    """Run the LangGraph qualify_node for one place; raises on validation or LLM error."""
    info = activity.info()
    with activity_span("qualify_lead", workflow_id=info.workflow_id or "", lead_id=place.id):
        state: LeadProcessingState = {
            "outreach_goal": outreach_goal,
            "sender_context": "",
            "place": place,
            "verdict": None,
            "email": None,
            "error": None,
        }
        patch = await asyncio.to_thread(qualify_node, state)
        if patch.get("error") is not None:
            raise RuntimeError(patch["error"])
        verdict = patch.get("verdict")
        if verdict is None:
            raise RuntimeError("qualify_node returned no verdict")
        return verdict


@activity.defn
async def generate_email_activity(
    outreach_goal: str,
    place: PlaceDetails,
    verdict: QualifierVerdict,
    sender_context: str,
) -> GeneratedEmail:
    """Draft a personalised cold-outreach email via the LangGraph email_node."""
    info = activity.info()
    with activity_span("generate_email", workflow_id=info.workflow_id or "", lead_id=place.id):
        state: LeadProcessingState = {
            "outreach_goal": outreach_goal,
            "sender_context": sender_context,
            "place": place,
            "verdict": verdict,
            "email": None,
            "error": None,
        }
        patch = await asyncio.to_thread(email_node, state)
        if patch.get("error") is not None:
            raise RuntimeError(patch["error"])
        email = patch.get("email")
        if email is None:
            raise RuntimeError("email_node returned no email")
        return email


@activity.defn
async def persist_phase_result_activity(
    run_id: str,
    status: str,
    scraped: int,
    qualified: int,
    emails_generated: int,
    leads: list[Lead],
) -> None:
    """Write phase results to the DB so the status endpoint can serve partial data.

    Called by the workflow at two points:
      1. After the qualify phase (status='generating', leads=qualify_leads)
      2. After the email phase   (status='completed',  leads=all_leads)
    """
    from ai_worker.db import RunRow, session_factory

    leads_json = json.dumps([json.loads(lead.model_dump_json()) for lead in leads])
    async with session_factory()() as db:
        row: RunRow | None = await db.get(RunRow, run_id)
        if row is None:
            return
        row.status = status
        row.scraped = scraped
        row.qualified = qualified
        row.emails_generated = emails_generated
        row.leads_json = leads_json
        await db.commit()
