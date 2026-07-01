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
        GET_DETAILS_RETRY,
        GET_DETAILS_TIMEOUT,
        PERSIST_RETRY,
        PERSIST_TIMEOUT,
        QUALIFY_RETRY,
        QUALIFY_TIMEOUT,
        SEARCH_RETRY,
        SEARCH_TIMEOUT,
        generate_email_activity,
        get_place_details_activity,
        persist_phase_result_activity,
        qualify_lead_activity,
        search_places_activity,
    )
    from shared.schemas import (
        GeneratedEmail,
        Lead,
        PlaceDetails,
        PlaceSearchResult,
        QualifierVerdict,
    )


# ── Workflow I/O dataclasses ───────────────────────────────────────────────────


@dataclass
class LeadGenInput:
    prompt: str
    target_query: str
    limit: int = 20
    sender_context: str = ""
    max_concurrency: int = 10


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


# ── Workflow ───────────────────────────────────────────────────────────────────


@workflow.defn
class LeadGenerationWorkflow:
    def __init__(self) -> None:
        self._progress = WorkflowProgress(stage="scraping")

    @workflow.run
    async def run(self, input: LeadGenInput) -> LeadGenOutput:
        sem = asyncio.Semaphore(input.max_concurrency)

        # 1. Search ────────────────────────────────────────────────────────────
        self._progress = WorkflowProgress(stage="scraping")
        results: list[PlaceSearchResult] = await workflow.execute_activity(
            search_places_activity,
            args=[input.target_query, input.limit],
            start_to_close_timeout=SEARCH_TIMEOUT,
            retry_policy=SEARCH_RETRY,
        )
        self._progress = WorkflowProgress(stage="getting_details", total=len(results))

        # 2. Enrich (parallel) ─────────────────────────────────────────────────
        async def _fetch_details(r: PlaceSearchResult) -> PlaceDetails:
            async with sem:
                return await workflow.execute_activity(
                    get_place_details_activity,
                    r.id,
                    start_to_close_timeout=GET_DETAILS_TIMEOUT,
                    retry_policy=GET_DETAILS_RETRY,
                )

        places: list[PlaceDetails] = list(
            await asyncio.gather(*[_fetch_details(r) for r in results])
        )
        self._progress = WorkflowProgress(stage="qualifying", total=len(places))

        # 3. Qualify (parallel, partial failure → Lead.error) ──────────────────
        async def _qualify(place: PlaceDetails) -> Lead:
            async with sem:
                try:
                    verdict: QualifierVerdict = await workflow.execute_activity(
                        qualify_lead_activity,
                        args=[input.prompt, place],
                        start_to_close_timeout=QUALIFY_TIMEOUT,
                        retry_policy=QUALIFY_RETRY,
                    )
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
        # Persist partial results so status endpoint can serve them immediately
        await workflow.execute_activity(
            persist_phase_result_activity,
            args=[
                workflow.info().workflow_id,
                "generating",
                len(places),
                len(qualified_pairs),
                0,
                qualify_leads,
            ],
            start_to_close_timeout=PERSIST_TIMEOUT,
            retry_policy=PERSIST_RETRY,
        )
        self._progress = WorkflowProgress(
            stage="generating",
            total=len(places),
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
            lead for lead in qualify_leads if lead.verdict is None or not lead.verdict.is_qualified
        ]
        all_leads: list[Lead] = unqualified + email_leads

        # Persist final results before completing
        await workflow.execute_activity(
            persist_phase_result_activity,
            args=[
                workflow.info().workflow_id,
                "completed",
                len(places),
                len(qualified_pairs),
                emailed,
                all_leads,
            ],
            start_to_close_timeout=PERSIST_TIMEOUT,
            retry_policy=PERSIST_RETRY,
        )
        self._progress = WorkflowProgress(
            stage="completed",
            total=len(places),
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
        )

    @workflow.query
    def get_progress(self) -> WorkflowProgress:
        return self._progress
