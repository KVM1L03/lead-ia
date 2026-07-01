"""Temporal activities — all side-effecting work lives here.

Workflows schedule these; nodes in agent_graph are NOT imported here to
avoid circular imports (activities → workflow would create a cycle).
"""

import asyncio
import json
import sys
from datetime import timedelta
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import TextContent
from temporalio import activity
from temporalio.common import RetryPolicy

from ai_worker.dspy_engine import generate_email, qualify_lead
from ai_worker.llm_router import get_lm
from shared.schemas import GeneratedEmail, PlaceDetails, PlaceSearchResult, QualifierVerdict

# ── Timeout defaults — referenced by workflows when scheduling ─────────────────
SEARCH_TIMEOUT = timedelta(seconds=60)
QUALIFY_TIMEOUT = timedelta(seconds=30)
EMAIL_TIMEOUT = timedelta(seconds=60)

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
QUALIFY_RETRY = RetryPolicy(
    maximum_attempts=3,
    non_retryable_error_types=_NON_RETRYABLE,
)
EMAIL_RETRY = RetryPolicy(
    maximum_attempts=3,
    non_retryable_error_types=_NON_RETRYABLE,
)

# ── MCP server parameters ──────────────────────────────────────────────────────
_MAPS_SERVER = StdioServerParameters(
    command=sys.executable,
    args=["maps_bridge/server.py"],
)


async def _call_search_places(query: str, limit: int) -> list[PlaceSearchResult]:
    """Spawn maps_bridge via stdio and call the search_places MCP tool."""
    async with stdio_client(_MAPS_SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("search_places", {"query": query, "limit": limit})
    if result.isError:
        raise RuntimeError(f"MCP tool returned an error: {result.content}")
    text_block = next((c for c in result.content if isinstance(c, TextContent)), None)
    if text_block is None:
        raise RuntimeError("MCP search_places returned no text content")
    raw: list[Any] = json.loads(text_block.text)
    return [PlaceSearchResult.model_validate(item) for item in raw]


# ── Activities ─────────────────────────────────────────────────────────────────


@activity.defn
async def search_places_activity(query: str, limit: int) -> list[PlaceSearchResult]:
    """Call maps_bridge MCP server to search Google Places."""
    return await _call_search_places(query, limit)


@activity.defn
async def qualify_lead_activity(outreach_goal: str, place: PlaceDetails) -> QualifierVerdict:
    """Run the DSPy qualifier for one place; raises on validation or LLM error."""
    return await asyncio.to_thread(qualify_lead, outreach_goal, place, lm=get_lm("qualifier"))


@activity.defn
async def generate_email_activity(
    outreach_goal: str,
    place: PlaceDetails,
    verdict: QualifierVerdict,
    sender_context: str,
) -> GeneratedEmail:
    """Draft a personalised cold-outreach email for a qualified lead."""
    return await asyncio.to_thread(
        generate_email,
        outreach_goal,
        place,
        qualifier_reasoning=verdict.reasoning,
        sender_context=sender_context,
        lm=get_lm("email"),
    )
