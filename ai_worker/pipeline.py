"""Core pipeline business logic — shared between Temporal activities and sync path.

Temporal path: activities.py wraps these functions with @activity.defn + retry policies.
Sync path: api_gateway/routes/leads.py calls run_pipeline() directly.

Never import from activities.py here — that would create a circular dependency.
Import chain: pipeline.py → dspy_engine.py, llm_router.py, maps_bridge (via MCP)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent

from ai_worker.dspy_engine import generate_email, qualify_lead
from ai_worker.llm_router import get_lm
from shared.schemas import GeneratedEmail, Lead, PlaceDetails, PlaceSearchResult, QualifierVerdict

# ── MCP transport selection ────────────────────────────────────────────────────
# MAPS_TRANSPORT=stdio  (default): spawn maps_bridge as a subprocess via MCP stdio.
#   Zero-trust boundary is an OS process boundary — identical to local dev.
# MAPS_TRANSPORT=inline (Cloud Run): call maps_bridge provider in-process.
#   Zero-trust boundary becomes a module boundary; SerpAPI imports remain
#   exclusively in maps_bridge/ — never in ai_worker/ code.
_MAPS_TRANSPORT: str = os.environ.get("MAPS_TRANSPORT", "stdio")

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


async def _call_search_places_stdio(query: str, limit: int) -> list[PlaceSearchResult]:
    """Spawn maps_bridge via stdio and call the search_places MCP tool."""
    async with stdio_client(_MAPS_SERVER) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool("search_places", {"query": query, "limit": limit})
    raw = _extract_tool_payload(result)
    if not isinstance(raw, list):
        raise RuntimeError(f"MCP search_places returned unexpected payload: {type(raw).__name__}")
    return [PlaceSearchResult.model_validate(item) for item in raw]


async def _call_get_place_details_stdio(place_id: str) -> PlaceDetails:
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


async def _call_search_places_inline(query: str, limit: int) -> list[PlaceSearchResult]:
    """Call maps_bridge provider in-process (Cloud Run inline mode).

    Lazy import keeps maps_bridge.providers.serpapi out of ai_worker's namespace —
    zero-trust is preserved at module level even when running in the same process.
    """
    from maps_bridge.provider_factory import get_provider

    return list(await get_provider().search_places(query, limit))


async def _call_get_place_details_inline(place_id: str) -> PlaceDetails:
    """Call maps_bridge provider in-process (Cloud Run inline mode)."""
    from maps_bridge.provider_factory import get_provider

    return await get_provider().get_place_details(place_id)


# ── Public API — called by both activities and sync path ────────────────────────


async def search_places(query: str, limit: int) -> list[PlaceSearchResult]:
    """Search Google Places via maps_bridge. Transport selected by MAPS_TRANSPORT."""
    if _MAPS_TRANSPORT == "inline":
        return await _call_search_places_inline(query, limit)
    return await _call_search_places_stdio(query, limit)


async def get_place_details(place_id: str) -> PlaceDetails:
    """Fetch full place details via maps_bridge. Transport selected by MAPS_TRANSPORT."""
    if _MAPS_TRANSPORT == "inline":
        return await _call_get_place_details_inline(place_id)
    return await _call_get_place_details_stdio(place_id)


async def qualify_lead_async(outreach_goal: str, place: PlaceDetails) -> QualifierVerdict:
    """Async wrapper: runs DSPy qualify_lead in a thread (blocking call).

    Uses dspy.context(lm=...) per-call — safe under concurrent asyncio tasks
    (avoids the dspy.configure() race condition described in CLAUDE.md §11).
    """
    return await asyncio.to_thread(qualify_lead, outreach_goal, place, lm=get_lm("qualifier"))


async def generate_email_async(
    outreach_goal: str,
    place: PlaceDetails,
    verdict: QualifierVerdict,
    sender_context: str,
) -> GeneratedEmail:
    """Async wrapper: runs DSPy generate_email in a thread (blocking call)."""
    return await asyncio.to_thread(
        generate_email,
        outreach_goal,
        place,
        qualifier_reasoning=verdict.reasoning,
        sender_context=sender_context,
        lm=get_lm("email"),
    )


async def run_pipeline(
    prompt: str,
    target_query: str,
    limit: int,
    sender_context: str,
    max_concurrency: int = 10,
) -> list[Lead]:
    """Run the full lead-generation pipeline synchronously (no Temporal).

    Called by the sync execution path (EXECUTION_MODE=sync). The Temporal path
    calls search_places(), get_place_details(), qualify_lead_async(), and
    generate_email_async() individually via activities with retry policies.

    Both paths share the same functions — no divergent business logic.

    Uses asyncio.gather for per-lead fan-out — N leads don't run sequentially.
    max_concurrency limits simultaneous MCP + LLM calls via a semaphore.
    """
    sem = asyncio.Semaphore(max_concurrency)

    # 1. Search ─────────────────────────────────────────────────────────────────
    results: list[PlaceSearchResult] = await search_places(target_query, limit)

    # 2. Enrich (parallel) ──────────────────────────────────────────────────────
    async def _fetch(r: PlaceSearchResult) -> PlaceDetails:
        async with sem:
            return await get_place_details(r.id)

    places: list[PlaceDetails] = list(await asyncio.gather(*[_fetch(r) for r in results]))

    # 3. Qualify (parallel, partial failure → Lead.error) ───────────────────────
    async def _qualify(place: PlaceDetails) -> Lead:
        async with sem:
            try:
                verdict = await qualify_lead_async(prompt, place)
                return Lead(place=place, verdict=verdict)
            except Exception as exc:
                root = exc.__cause__ if exc.__cause__ is not None else exc
                return Lead(place=place, error=str(root))

    qualify_leads: list[Lead] = list(await asyncio.gather(*[_qualify(p) for p in places]))
    qualified_pairs: list[tuple[PlaceDetails, QualifierVerdict]] = [
        (lead.place, lead.verdict)
        for lead in qualify_leads
        if lead.verdict is not None and lead.verdict.is_qualified
    ]

    # 4. Email (parallel, partial failure → Lead without email) ─────────────────
    async def _email(place: PlaceDetails, verdict: QualifierVerdict) -> Lead:
        async with sem:
            try:
                email = await generate_email_async(prompt, place, verdict, sender_context)
                return Lead(place=place, verdict=verdict, email=email)
            except Exception as exc:
                root = exc.__cause__ if exc.__cause__ is not None else exc
                return Lead(place=place, verdict=verdict, error=str(root))

    email_leads: list[Lead] = list(
        await asyncio.gather(*[_email(p, v) for p, v in qualified_pairs])
    )

    unqualified = [
        lead for lead in qualify_leads if lead.verdict is None or not lead.verdict.is_qualified
    ]
    return unqualified + email_leads
