"""Temporal workflow — deterministic orchestrator for the lead pipeline.

All I/O lives in activities. This file is pure control flow: no HTTP, no LLM
calls, no datetime.now(), no uuid4(). Replay-safe by construction.

DTOs (LeadGenInput, LeadGenOutput, WorkflowProgress) are Python @dataclasses
rather than Pydantic models so that Temporal's payload converter handles them
natively. list[Lead] inside LeadGenOutput is serialised via pydantic_data_converter
which must be passed to both Client.connect() and WorkflowEnvironment.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime

from temporalio import workflow
from temporalio.worker.workflow_sandbox import SandboxedWorkflowRunner, SandboxRestrictions

# beartype installs import hooks that cause circular imports inside Temporal's
# sandbox when other tests (importing DSPy) have already loaded beartype.
# Pass it through so the sandbox uses the already-loaded module.
SANDBOXED_RUNNER = SandboxedWorkflowRunner(
    restrictions=SandboxRestrictions.default.with_passthrough_modules("beartype")
)

with workflow.unsafe.imports_passed_through():
    # Activity imports must be guarded so the sandbox doesn't intercept them
    # at import time — they are only called via workflow.execute_activity().
    from ai_worker.activities import (
        EMAIL_RETRY,
        EMAIL_TIMEOUT,
        EXPAND_QUERY_RETRY,
        EXPAND_QUERY_TIMEOUT,
        GET_DETAILS_RETRY,
        GET_DETAILS_TIMEOUT,
        PERSIST_RETRY,
        PERSIST_TIMEOUT,
        QUALIFY_RETRY,
        QUALIFY_TIMEOUT,
        SEARCH_RETRY,
        SEARCH_TIMEOUT,
        expand_search_query_activity,
        generate_email_activity,
        get_place_details_activity,
        persist_phase_result_activity,
        qualify_lead_activity,
        search_places_activity,
    )
    from ai_worker.agent_graph import build_lead_state, should_generate_email
    from shared.schemas import (
        ExpansionDecision,
        GeneratedEmail,
        Lead,
        PlaceDetails,
        PlaceSearchResult,
        QualifierVerdict,
    )

# Backfill round cap — see docs/adr/0001-backfill-temporal-only.md and CONTEXT.md § Backfill.
MAX_BACKFILL_ROUNDS = 2


def _lead_should_generate_email(lead: Lead, outreach_goal: str, sender_context: str) -> bool:
    """Route through the shared agent_graph predicate — do not reimplement it here."""
    return should_generate_email(
        build_lead_state(
            outreach_goal=outreach_goal,
            place=lead.place,
            sender_context=sender_context,
            verdict=lead.verdict,
            email=lead.email,
            error=lead.error,
        )
    )


def _qualified_pair(
    lead: Lead, outreach_goal: str, sender_context: str
) -> tuple[PlaceDetails, QualifierVerdict] | None:
    if not _lead_should_generate_email(lead, outreach_goal, sender_context):
        return None
    verdict = lead.verdict
    assert verdict is not None
    return (lead.place, verdict)


# ── Workflow I/O dataclasses ───────────────────────────────────────────────────


@dataclass
class LeadGenInput:
    prompt: str
    target_query: str
    limit: int = 20
    sender_context: str = ""
    max_concurrency: int = 10
    maps_provider: str | None = None


@dataclass
class WorkflowProgress:
    stage: str = "scraping"
    total: int = 0
    qualified: int = 0
    emailed: int = 0


@dataclass
class LeadGenOutput:
    run_id: str
    prompt: str
    target_query: str
    limit: int
    leads: list[Lead] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    backfill_exhausted: bool = False
    tried_cities: list[str] = field(default_factory=list)
    tried_industries: list[str] = field(default_factory=list)


# ── Workflow ───────────────────────────────────────────────────────────────────


@workflow.defn
class LeadGenerationWorkflow:
    def __init__(self) -> None:
        self._progress = WorkflowProgress(stage="scraping")

    @workflow.run
    async def run(self, input: LeadGenInput) -> LeadGenOutput:
        """Temporal execution path: search → enrich → qualify → email (durable, replayable).

        DELIBERATE MIRROR of run_pipeline (ai_worker/pipeline.py) — same four-step order.
        Not unified because Temporal workflows are 100% deterministic: no direct HTTP, LLM,
        or MCP calls allowed — all I/O goes through activities with explicit retry policies.
        The two models also differ in concurrency (workflow semaphore is replay-safe), error
        handling (per-activity retry vs. gather-level wrapping), and progress tracking
        (@workflow.query). Leaf logic is shared: qualify_node and email_node in agent_graph.py,
        called here via qualify_lead_activity / generate_email_activity, and in the sync path
        via process_one_lead.
        """
        sem = asyncio.Semaphore(input.max_concurrency)

        # 1. Search ────────────────────────────────────────────────────────────
        self._progress = WorkflowProgress(stage="scraping")
        results: list[PlaceSearchResult] = await workflow.execute_activity(
            search_places_activity,
            args=[input.target_query, input.limit, input.maps_provider],
            start_to_close_timeout=SEARCH_TIMEOUT,
            retry_policy=SEARCH_RETRY,
        )
        self._progress = WorkflowProgress(stage="getting_details", total=len(results))

        # 2. Enrich (parallel) ─────────────────────────────────────────────────
        async def _fetch_details(r: PlaceSearchResult) -> PlaceDetails:
            async with sem:
                return await workflow.execute_activity(
                    get_place_details_activity,
                    args=[r.id, input.maps_provider],
                    start_to_close_timeout=GET_DETAILS_TIMEOUT,
                    retry_policy=GET_DETAILS_RETRY,
                )

        places: list[PlaceDetails] = list(
            await asyncio.gather(*[_fetch_details(r) for r in results])
        )
        self._progress = WorkflowProgress(stage="qualifying", total=len(places))

        # 3. Qualify (parallel, partial failure → Lead.error) ──────────────────
        async def _qualify(place: PlaceDetails, outreach_goal: str) -> Lead:
            async with sem:
                try:
                    verdict: QualifierVerdict = await workflow.execute_activity(
                        qualify_lead_activity,
                        args=[outreach_goal, place],
                        start_to_close_timeout=QUALIFY_TIMEOUT,
                        retry_policy=QUALIFY_RETRY,
                    )
                    return Lead(place=place, verdict=verdict)
                except Exception as exc:
                    root = exc.__cause__ if exc.__cause__ is not None else exc
                    return Lead(place=place, error=str(root))

        qualify_leads: list[Lead] = list(
            await asyncio.gather(*[_qualify(p, input.prompt) for p in places])
        )
        qualified_pairs: list[tuple[PlaceDetails, QualifierVerdict]] = [
            pair
            for lead in qualify_leads
            if (pair := _qualified_pair(lead, input.prompt, input.sender_context)) is not None
        ]
        total_scraped = len(places)

        # 3b. Backfill (Temporal-only reactive search-expansion loop) ──────────
        # See CONTEXT.md § Backfill / Shortfall / Strategy axis and
        # docs/adr/0001-backfill-temporal-only.md, 0002-backfill-single-final-email-pass.md.
        seen_place_ids: set[str] = {r.id for r in results}
        tried_cities: list[str] = []
        tried_industries: list[str] = []
        backfill_round = 0
        while len(qualified_pairs) < input.limit and backfill_round < MAX_BACKFILL_ROUNDS:
            backfill_round += 1
            shortfall = input.limit - len(qualified_pairs)

            decision: ExpansionDecision = await workflow.execute_activity(
                expand_search_query_activity,
                args=[input.prompt, input.target_query, tried_cities, tried_industries, shortfall],
                start_to_close_timeout=EXPAND_QUERY_TIMEOUT,
                retry_policy=EXPAND_QUERY_RETRY,
            )
            if decision.strategy == "city":
                tried_cities.append(decision.axis_value)
                # Widen the ICP geography for this round's qualify calls only — the
                # original prompt still names the original city, so without this every
                # newly-searched place gets rejected for a geo mismatch. See CONTEXT.md
                # § Backfill / Strategy axis.
                round_outreach_goal = (
                    f"{input.prompt} Also accept businesses located in {decision.axis_value}."
                )
            else:
                tried_industries.append(decision.axis_value)
                round_outreach_goal = input.prompt

            round_results: list[PlaceSearchResult] = await workflow.execute_activity(
                search_places_activity,
                args=[decision.target_query, shortfall, input.maps_provider],
                start_to_close_timeout=SEARCH_TIMEOUT,
                retry_policy=SEARCH_RETRY,
            )
            new_results = [r for r in round_results if r.id not in seen_place_ids]
            seen_place_ids.update(r.id for r in new_results)

            new_places: list[PlaceDetails] = list(
                await asyncio.gather(*[_fetch_details(r) for r in new_results])
            )
            total_scraped += len(new_places)

            new_qualify_leads: list[Lead] = list(
                await asyncio.gather(*[_qualify(p, round_outreach_goal) for p in new_places])
            )
            new_qualified_pairs = [
                pair
                for lead in new_qualify_leads
                if (pair := _qualified_pair(lead, round_outreach_goal, input.sender_context))
                is not None
            ]
            qualify_leads += new_qualify_leads
            qualified_pairs += new_qualified_pairs

            if not new_qualified_pairs:
                break

        backfill_exhausted = backfill_round > 0 and len(qualified_pairs) < input.limit

        # Persist partial results so status endpoint can serve them immediately.
        # Must pass all 9 positional args every call: Temporal's payload decoder
        # only applies the activity's type hints when the input count matches the
        # function signature exactly, else it silently falls back to untyped dicts
        # (temporalio/worker/_activity.py) — omitting the trailing optional args
        # here previously deserialized `leads` as list[dict], not list[Lead].
        await workflow.execute_activity(
            persist_phase_result_activity,
            args=[
                workflow.info().workflow_id,
                "generating",
                total_scraped,
                len(qualified_pairs),
                0,
                qualify_leads,
                backfill_exhausted,
                tried_cities,
                tried_industries,
            ],
            start_to_close_timeout=PERSIST_TIMEOUT,
            retry_policy=PERSIST_RETRY,
        )
        self._progress = WorkflowProgress(
            stage="generating",
            total=total_scraped,
            qualified=len(qualified_pairs),
        )

        # 4. Email (parallel, partial failure → Lead without email) ───────────
        async def _email(place: PlaceDetails, verdict: QualifierVerdict) -> Lead:
            async with sem:
                try:
                    email: GeneratedEmail = await workflow.execute_activity(
                        generate_email_activity,
                        args=[input.prompt, place, verdict, input.sender_context or input.prompt],
                        start_to_close_timeout=EMAIL_TIMEOUT,
                        retry_policy=EMAIL_RETRY,
                    )
                    return Lead(place=place, verdict=verdict, email=email)
                except Exception as exc:
                    root = exc.__cause__ if exc.__cause__ is not None else exc
                    return Lead(place=place, verdict=verdict, error=str(root))

        email_leads: list[Lead] = list(
            await asyncio.gather(*[_email(p, v) for p, v in qualified_pairs])
        )
        emailed = sum(1 for lead in email_leads if lead.email is not None)

        unqualified = [
            lead
            for lead in qualify_leads
            if not _lead_should_generate_email(lead, input.prompt, input.sender_context)
        ]
        all_leads: list[Lead] = unqualified + email_leads

        # Persist final results before completing
        await workflow.execute_activity(
            persist_phase_result_activity,
            args=[
                workflow.info().workflow_id,
                "completed",
                total_scraped,
                len(qualified_pairs),
                emailed,
                all_leads,
                backfill_exhausted,
                tried_cities,
                tried_industries,
            ],
            start_to_close_timeout=PERSIST_TIMEOUT,
            retry_policy=PERSIST_RETRY,
        )
        self._progress = WorkflowProgress(
            stage="completed",
            total=total_scraped,
            qualified=len(qualified_pairs),
            emailed=emailed,
        )
        return LeadGenOutput(
            run_id=workflow.info().workflow_id,
            prompt=input.prompt,
            target_query=input.target_query,
            limit=input.limit,
            leads=all_leads,
            created_at=workflow.now(),
            backfill_exhausted=backfill_exhausted,
            tried_cities=tried_cities,
            tried_industries=tried_industries,
        )

    @workflow.query
    def get_progress(self) -> WorkflowProgress:
        return self._progress
