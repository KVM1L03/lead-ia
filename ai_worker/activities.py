"""Temporal activities — all side-effecting work lives here.

Workflows schedule these; nodes in agent_graph are NOT imported here to
avoid circular imports (activities → workflow would create a cycle).
"""

import asyncio
import json
import os
import sys
from datetime import timedelta
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent
from temporalio import activity
from temporalio.common import RetryPolicy

from ai_worker.dspy_engine import generate_email, qualify_lead
from ai_worker.llm_router import get_lm
from ai_worker.observability import activity_span
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

# ── MCP server parameters ──────────────────────────────────────────────────────
_APP_ROOT = os.environ.get("PYTHONPATH", "/app").split(os.pathsep)[0] or "/app"
_MAPS_SERVER = StdioServerParameters(
    command=sys.executable,
    args=["-m", "maps_bridge.server"],
    env={**os.environ, "PYTHONPATH": _APP_ROOT},
    cwd=_APP_ROOT,
)


def _extract_tool_payload(result: CallToolResult) -> Any:
    """Parse MCP tool output from TextContent and/or FastMCP structuredContent."""
    if result.isError:
        raise RuntimeError(f"MCP tool returned an error: {result.content}")

    text_block = next((c for c in result.content if isinstance(c, TextContent)), None)
    if text_block is not None:
        return json.loads(text_block.text)

    structured = result.structuredContent
    if structured is None:
        raise RuntimeError("MCP tool returned no content")
    if isinstance(structured, dict) and "result" in structured:
        return structured["result"]
    return structured


async def _call_search_places(query: str, limit: int) -> list[PlaceSearchResult]:
    """Spawn maps_bridge via stdio and call the search_places MCP tool."""
    async with stdio_client(_MAPS_SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("search_places", {"query": query, "limit": limit})
    raw = _extract_tool_payload(result)
    if not isinstance(raw, list):
        raise RuntimeError(f"MCP search_places returned unexpected payload: {type(raw).__name__}")
    return [PlaceSearchResult.model_validate(item) for item in raw]


async def _call_get_place_details(place_id: str) -> PlaceDetails:
    """Spawn maps_bridge via stdio and call the get_place_details MCP tool."""
    async with stdio_client(_MAPS_SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("get_place_details", {"place_id": place_id})
    raw = _extract_tool_payload(result)
    if not isinstance(raw, dict):
        raise RuntimeError(
            f"MCP get_place_details returned unexpected payload: {type(raw).__name__}"
        )
    return PlaceDetails.model_validate(raw)


# ── Activities ─────────────────────────────────────────────────────────────────


@activity.defn
async def search_places_activity(query: str, limit: int) -> list[PlaceSearchResult]:
    """Call maps_bridge MCP server to search Google Places."""
    info = activity.info()
    with activity_span("search_places", workflow_id=info.workflow_id or ""):
        return await _call_search_places(query, limit)


@activity.defn
async def get_place_details_activity(place_id: str) -> PlaceDetails:
    """Fetch full place details from maps_bridge MCP server."""
    info = activity.info()
    with activity_span("get_place_details", workflow_id=info.workflow_id or "", lead_id=place_id):
        return await _call_get_place_details(place_id)


@activity.defn
async def qualify_lead_activity(outreach_goal: str, place: PlaceDetails) -> QualifierVerdict:
    """Run the DSPy qualifier for one place; raises on validation or LLM error."""
    info = activity.info()
    with activity_span("qualify_lead", workflow_id=info.workflow_id or "", lead_id=place.id):
        return await asyncio.to_thread(qualify_lead, outreach_goal, place, lm=get_lm("qualifier"))


@activity.defn
async def generate_email_activity(
    outreach_goal: str,
    place: PlaceDetails,
    verdict: QualifierVerdict,
    sender_context: str,
) -> GeneratedEmail:
    """Draft a personalised cold-outreach email for a qualified lead."""
    info = activity.info()
    with activity_span("generate_email", workflow_id=info.workflow_id or "", lead_id=place.id):
        return await asyncio.to_thread(
            generate_email,
            outreach_goal,
            place,
            qualifier_reasoning=verdict.reasoning,
            sender_context=sender_context,
            lm=get_lm("email"),
        )


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
