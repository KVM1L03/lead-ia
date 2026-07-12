"""Core pipeline business logic — shared between Temporal activities and sync path.

Temporal path: activities.py wraps graph nodes with @activity.defn + retry policies.
Sync path: api_gateway/routes/leads.py calls run_pipeline() directly.

Never import from activities.py here — that would create a circular dependency.
Import chain: pipeline.py → agent_graph.py → dspy_engine.py, llm_router.py, maps_bridge (via MCP)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from types import TracebackType
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent

from ai_worker.agent_graph import LeadProcessingState, process_one_lead
from shared.schemas import Lead, PlaceDetails, PlaceSearchResult

# ── MCP transport selection ────────────────────────────────────────────────────
# MAPS_TRANSPORT=stdio  (default): spawn maps_bridge as a subprocess via MCP stdio.
#   Zero-trust boundary is an OS process boundary — identical to local dev.
# MAPS_TRANSPORT=inline (Cloud Run): call maps_bridge provider in-process.
#   Zero-trust boundary becomes a module boundary; SerpAPI imports remain
#   exclusively in maps_bridge/ — never in ai_worker/ code.
_MAPS_TRANSPORT: str = os.environ.get("MAPS_TRANSPORT", "stdio")

_APP_ROOT = os.environ.get("PYTHONPATH", "/app").split(os.pathsep)[0] or "/app"

SearchPlacesFn = Callable[
    [str, int, str | None],
    Awaitable[list[PlaceSearchResult]],
]
GetPlaceDetailsFn = Callable[[str, str | None], Awaitable[PlaceDetails]]


def _stdio_server_params(maps_provider: str | None = None) -> StdioServerParameters:
    env = {**os.environ, "PYTHONPATH": _APP_ROOT}
    if maps_provider is not None:
        env["MAPS_PROVIDER"] = maps_provider
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "maps_bridge.server"],
        env=env,
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


def _parse_search_places_result(result: CallToolResult) -> list[PlaceSearchResult]:
    raw = _extract_tool_payload(result)
    if not isinstance(raw, list):
        raise RuntimeError(f"MCP search_places returned unexpected payload: {type(raw).__name__}")
    return [PlaceSearchResult.model_validate(item) for item in raw]


def _parse_place_details_result(result: CallToolResult) -> PlaceDetails:
    raw = _extract_tool_payload(result)
    if not isinstance(raw, dict):
        raise RuntimeError(
            f"MCP get_place_details returned unexpected payload: {type(raw).__name__}"
        )
    return PlaceDetails.model_validate(raw)


class MapsMcpSession:
    """Reusable stdio MCP session for one sync pipeline run."""

    def __init__(self, maps_provider: str | None = None) -> None:
        self._maps_provider = maps_provider
        self._stack = AsyncExitStack()
        self._session: ClientSession | None = None

    async def __aenter__(self) -> MapsMcpSession:
        read, write = await self._stack.enter_async_context(
            stdio_client(_stdio_server_params(self._maps_provider))
        )
        session = await self._stack.enter_async_context(ClientSession(read, write))
        await session.initialize()
        self._session = session
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        self._session = None
        return await self._stack.__aexit__(exc_type, exc, tb)

    @property
    def session(self) -> ClientSession:
        if self._session is None:
            raise RuntimeError("MCP session is not initialized")
        return self._session

    async def search_places(
        self,
        query: str,
        limit: int,
        maps_provider: str | None = None,
    ) -> list[PlaceSearchResult]:
        result = await self.session.call_tool("search_places", {"query": query, "limit": limit})
        return _parse_search_places_result(result)

    async def get_place_details(
        self,
        place_id: str,
        maps_provider: str | None = None,
    ) -> PlaceDetails:
        result = await self.session.call_tool("get_place_details", {"place_id": place_id})
        return _parse_place_details_result(result)


async def _call_search_places_stdio(
    query: str,
    limit: int,
    maps_provider: str | None = None,
) -> list[PlaceSearchResult]:
    """Spawn maps_bridge via stdio and call the search_places MCP tool."""
    async with MapsMcpSession(maps_provider) as session:
        return await session.search_places(query, limit)


async def _call_get_place_details_stdio(
    place_id: str,
    maps_provider: str | None = None,
) -> PlaceDetails:
    """Spawn maps_bridge via stdio and call the get_place_details MCP tool."""
    async with MapsMcpSession(maps_provider) as session:
        return await session.get_place_details(place_id)


async def _call_search_places_inline(
    query: str,
    limit: int,
    maps_provider: str | None = None,
) -> list[PlaceSearchResult]:
    """Call maps_bridge provider in-process (Cloud Run inline mode).

    Lazy import keeps maps_bridge.providers.serpapi out of ai_worker's namespace —
    zero-trust is preserved at module level even when running in the same process.
    """
    from maps_bridge.provider_factory import get_provider

    return list(await get_provider(maps_provider).search_places(query, limit))


async def _call_get_place_details_inline(
    place_id: str,
    maps_provider: str | None = None,
) -> PlaceDetails:
    """Call maps_bridge provider in-process (Cloud Run inline mode)."""
    from maps_bridge.provider_factory import get_provider

    return await get_provider(maps_provider).get_place_details(place_id)


# ── Public API — called by both activities and sync path ────────────────────────


async def search_places(
    query: str,
    limit: int,
    maps_provider: str | None = None,
) -> list[PlaceSearchResult]:
    """Search Google Places via maps_bridge. Transport selected by MAPS_TRANSPORT."""
    if _MAPS_TRANSPORT == "inline":
        return await _call_search_places_inline(query, limit, maps_provider)
    return await _call_search_places_stdio(query, limit, maps_provider)


async def get_place_details(
    place_id: str,
    maps_provider: str | None = None,
) -> PlaceDetails:
    """Fetch full place details via maps_bridge. Transport selected by MAPS_TRANSPORT."""
    if _MAPS_TRANSPORT == "inline":
        return await _call_get_place_details_inline(place_id, maps_provider)
    return await _call_get_place_details_stdio(place_id, maps_provider)


async def run_pipeline(
    prompt: str,
    target_query: str,
    limit: int,
    sender_context: str,
    max_concurrency: int = 10,
    maps_provider: str | None = None,
) -> list[Lead]:
    """Sync execution path: search → enrich → qualify → email (EXECUTION_MODE=sync).

    DELIBERATE MIRROR of LeadGenerationWorkflow.run (ai_worker/workflows.py) — both follow
    the same four-step order. They are not unified because Temporal workflows cannot call
    external services directly (only through activities with explicit retry/timeout metadata),
    and the two models differ in error handling, concurrency primitives, progress tracking,
    and determinism constraints. The shared piece is the leaf logic: qualify_node and
    email_node in agent_graph.py, called here via process_one_lead, and in the Temporal
    path via qualify_lead_activity / generate_email_activity.

    Uses asyncio.gather for per-lead fan-out; max_concurrency limits simultaneous MCP +
    LLM calls via a semaphore.
    """
    if _MAPS_TRANSPORT == "stdio":
        async with MapsMcpSession(maps_provider) as session:
            return await _run_pipeline_with_maps(
                prompt=prompt,
                target_query=target_query,
                limit=limit,
                sender_context=sender_context,
                max_concurrency=max_concurrency,
                maps_provider=maps_provider,
                search_places_fn=session.search_places,
                get_place_details_fn=session.get_place_details,
            )

    return await _run_pipeline_with_maps(
        prompt=prompt,
        target_query=target_query,
        limit=limit,
        sender_context=sender_context,
        max_concurrency=max_concurrency,
        maps_provider=maps_provider,
        search_places_fn=search_places,
        get_place_details_fn=get_place_details,
    )


async def _run_pipeline_with_maps(
    prompt: str,
    target_query: str,
    limit: int,
    sender_context: str,
    max_concurrency: int,
    maps_provider: str | None,
    search_places_fn: SearchPlacesFn,
    get_place_details_fn: GetPlaceDetailsFn,
) -> list[Lead]:
    sem = asyncio.Semaphore(max_concurrency)

    # 1. Search ─────────────────────────────────────────────────────────────────
    results: list[PlaceSearchResult] = await search_places_fn(target_query, limit, maps_provider)

    # 2. Enrich (parallel) ──────────────────────────────────────────────────────
    async def _fetch(r: PlaceSearchResult) -> PlaceDetails | Lead:
        async with sem:
            try:
                return await get_place_details_fn(r.id, maps_provider)
            except Exception as exc:
                root = exc.__cause__ if exc.__cause__ is not None else exc
                fallback_place = PlaceDetails.model_validate(r.model_dump())
                return Lead(place=fallback_place, error=str(root))

    enriched: list[PlaceDetails | Lead] = list(await asyncio.gather(*[_fetch(r) for r in results]))

    # 3. Per-lead: qualify → decide → email via LangGraph graph (partial failure OK)
    async def _process(place: PlaceDetails) -> Lead:
        async with sem:
            state: LeadProcessingState = {
                "outreach_goal": prompt,
                "sender_context": sender_context,
                "place": place,
                "verdict": None,
                "email": None,
                "error": None,
            }
            try:
                return await asyncio.to_thread(process_one_lead, state)
            except Exception as exc:
                root = exc.__cause__ if exc.__cause__ is not None else exc
                return Lead(place=place, error=str(root))

    async def _process_enriched(item: PlaceDetails | Lead) -> Lead:
        if isinstance(item, Lead):
            return item
        return await _process(item)

    return list(await asyncio.gather(*[_process_enriched(item) for item in enriched]))
