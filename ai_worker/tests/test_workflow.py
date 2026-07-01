"""Integration tests for LeadGenerationWorkflow.

Uses WorkflowEnvironment.start_time_skipping() (downloads/caches temporal test
server binary on first run). All activities are replaced with deterministic mocks
registered under the real activity names so the workflow routes to them.

Replay test: run → fetch history → Replayer.replay_workflow() — verifies no
NondeterminismError, proving the workflow code is replay-safe.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from ai_worker.workflows import (
    SANDBOXED_RUNNER,
    LeadGenerationWorkflow,
    LeadGenInput,
    WorkflowProgress,
)
from shared.schemas import (
    GeneratedEmail,
    PlaceDetails,
    PlaceSearchResult,
    QualifierVerdict,
)

# ── Shared test data ───────────────────────────────────────────────────────────

_RESULT = PlaceSearchResult(
    id="place-001",
    name="Klinika Centrum",
    address="ul. Nowy Swiat 28, Warszawa",
    lat=52.233,
    lng=21.021,
    category="dental",
    rating=4.8,
    review_count=187,
)

_PLACE = PlaceDetails(
    id="place-001",
    name="Klinika Centrum",
    address="ul. Nowy Swiat 28, Warszawa",
    lat=52.233,
    lng=21.021,
    category="dental",
    rating=4.8,
    review_count=187,
    website="https://klinika.pl",
    phone="+48 22 826 1234",
    hours=["Mon-Fri 8:00-20:00"],
    photos=[],
)

_VERDICT_GOOD = QualifierVerdict(
    is_qualified=True,
    score=0.9,
    reasoning="Strong ICP fit.",
    icp_fit={"is_b2b": True, "has_website": True, "size_match": True},
)

_VERDICT_BAD = QualifierVerdict(
    is_qualified=False,
    score=0.1,
    reasoning="Does not fit ICP.",
    icp_fit={"is_b2b": False, "has_website": False, "size_match": False},
)

_EMAIL = GeneratedEmail(
    subject="Quick question about recalls at Klinika Centrum",
    body="Hi — saw your 4.8-star rating. We help dental clinics automate patient recalls.",
    personalization_hooks=["4.8-star rating", "Warsaw", "dental"],
    model_used="mock/test",
)

_INPUT = LeadGenInput(
    prompt="B2B dental SaaS for patient recalls",
    target_query="dentist Warsaw",
    limit=5,
    sender_context="I run a SaaS that automates dental recall campaigns.",
    max_concurrency=10,
)

# ── Fixture ────────────────────────────────────────────────────────────────────


@pytest.fixture
async def env() -> Any:
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as wf_env:
        yield wf_env


# ── Mock activity factories ────────────────────────────────────────────────────


def _make_mocks(
    n_places: int = 5,
    n_qualified: int = 3,
    qualify_raises_on: int | None = None,
    email_called_tracker: list[int] | None = None,
    concurrent_tracker: list[int] | None = None,
) -> list[Any]:
    """Return a list of mock @activity.defn functions matching real activity names."""
    qualify_call: list[int] = []

    @activity.defn(name="search_places_activity")
    async def mock_search(query: str, limit: int) -> list[PlaceSearchResult]:
        return [_RESULT] * n_places

    @activity.defn(name="get_place_details_activity")
    async def mock_details(place_id: str) -> PlaceDetails:
        return _PLACE

    @activity.defn(name="qualify_lead_activity")
    async def mock_qualify(outreach_goal: str, place: PlaceDetails) -> QualifierVerdict:
        idx = len(qualify_call)
        qualify_call.append(1)
        if qualify_raises_on is not None and idx == qualify_raises_on:
            raise ApplicationError("qualifier provider down", non_retryable=True)
        return _VERDICT_GOOD if idx < n_qualified else _VERDICT_BAD

    @activity.defn(name="generate_email_activity")
    async def mock_email(
        outreach_goal: str,
        place: PlaceDetails,
        verdict: QualifierVerdict,
        sender_context: str,
    ) -> GeneratedEmail:
        if email_called_tracker is not None:
            email_called_tracker.append(1)
        return _EMAIL

    return [mock_search, mock_details, mock_qualify, mock_email]


# ── Tests ──────────────────────────────────────────────────────────────────────


async def test_happy_path_5_places_3_qualified(env: WorkflowEnvironment) -> None:
    """5 places → 3 qualified get emails, 2 are not-qualified, no errors."""
    mocks = _make_mocks(n_places=5, n_qualified=3)

    async with Worker(
        env.client,
        task_queue="test-leads",
        workflows=[LeadGenerationWorkflow],
        workflow_runner=SANDBOXED_RUNNER,
        activities=mocks,
    ):
        result = await env.client.execute_workflow(
            LeadGenerationWorkflow.run,
            _INPUT,
            id="happy-path-wf",
            task_queue="test-leads",
        )

    assert len(result.leads) == 5
    qualified = [lead for lead in result.leads if lead.verdict and lead.verdict.is_qualified]
    assert len(qualified) == 3
    assert all(lead.email is not None for lead in qualified)
    not_qualified = [
        lead for lead in result.leads if lead.verdict and not lead.verdict.is_qualified
    ]
    assert len(not_qualified) == 2
    assert all(lead.email is None for lead in not_qualified)
    assert result.run_id == "happy-path-wf"


async def test_partial_qualify_failure_continues(env: WorkflowEnvironment) -> None:
    """One qualify call fails — the other 4 still complete; failed lead has error."""
    mocks = _make_mocks(n_places=5, n_qualified=3, qualify_raises_on=0)

    async with Worker(
        env.client,
        task_queue="test-leads",
        workflows=[LeadGenerationWorkflow],
        workflow_runner=SANDBOXED_RUNNER,
        activities=mocks,
    ):
        result = await env.client.execute_workflow(
            LeadGenerationWorkflow.run,
            _INPUT,
            id="partial-fail-wf",
            task_queue="test-leads",
        )

    assert len(result.leads) == 5
    error_leads = [lead for lead in result.leads if lead.error is not None]
    assert len(error_leads) == 1
    assert "qualifier provider down" in (error_leads[0].error or "")
    completed = [lead for lead in result.leads if lead.error is None]
    assert len(completed) == 4


async def test_zero_qualified_skips_email_stage(env: WorkflowEnvironment) -> None:
    """All places fail qualification — generate_email_activity must never be called."""
    email_tracker: list[int] = []
    mocks = _make_mocks(n_places=5, n_qualified=0, email_called_tracker=email_tracker)

    async with Worker(
        env.client,
        task_queue="test-leads",
        workflows=[LeadGenerationWorkflow],
        workflow_runner=SANDBOXED_RUNNER,
        activities=mocks,
    ):
        result = await env.client.execute_workflow(
            LeadGenerationWorkflow.run,
            _INPUT,
            id="zero-qualified-wf",
            task_queue="test-leads",
        )

    assert len(result.leads) == 5
    assert all(lead.email is None for lead in result.leads)
    assert email_tracker == [], "generate_email_activity must not be called"


async def test_replay_safety(env: WorkflowEnvironment) -> None:
    """Run workflow, capture history, replay — NondeterminismError must not be raised."""
    mocks = _make_mocks(n_places=5, n_qualified=3)

    async with Worker(
        env.client,
        task_queue="test-leads",
        workflows=[LeadGenerationWorkflow],
        workflow_runner=SANDBOXED_RUNNER,
        activities=mocks,
    ):
        handle = await env.client.start_workflow(
            LeadGenerationWorkflow.run,
            _INPUT,
            id="replay-safety-wf",
            task_queue="test-leads",
        )
        await handle.result()
        history = await handle.fetch_history()

    replayer = Replayer(workflows=[LeadGenerationWorkflow], workflow_runner=SANDBOXED_RUNNER)
    # Raises NondeterminismError if replay diverges
    await replayer.replay_workflow(history)


async def test_query_final_progress(env: WorkflowEnvironment) -> None:
    """After completion, get_progress() returns stage=completed with correct counts."""
    mocks = _make_mocks(n_places=5, n_qualified=3)

    async with Worker(
        env.client,
        task_queue="test-leads",
        workflows=[LeadGenerationWorkflow],
        workflow_runner=SANDBOXED_RUNNER,
        activities=mocks,
    ):
        handle = await env.client.start_workflow(
            LeadGenerationWorkflow.run,
            _INPUT,
            id="query-progress-wf",
            task_queue="test-leads",
        )
        await handle.result()
        progress: WorkflowProgress = await handle.query(LeadGenerationWorkflow.get_progress)

    assert progress.stage == "completed"
    assert progress.total == 5
    assert progress.qualified == 3
    assert progress.emailed == 3


async def test_max_concurrency_respected(env: WorkflowEnvironment) -> None:
    """Concurrent activity count never exceeds max_concurrency (set to 2)."""
    active: list[int] = []
    peak: list[int] = []

    @activity.defn(name="search_places_activity")
    async def _search(query: str, limit: int) -> list[PlaceSearchResult]:
        return [_RESULT] * 4

    @activity.defn(name="get_place_details_activity")
    async def _details(place_id: str) -> PlaceDetails:
        active.append(1)
        peak.append(sum(active))
        await asyncio.sleep(0)  # yield so other coroutines can start
        active.pop()
        return _PLACE

    @activity.defn(name="qualify_lead_activity")
    async def _qualify(outreach_goal: str, place: PlaceDetails) -> QualifierVerdict:
        return _VERDICT_GOOD

    @activity.defn(name="generate_email_activity")
    async def _email(
        outreach_goal: str, place: PlaceDetails, verdict: QualifierVerdict, sender: str
    ) -> GeneratedEmail:
        return _EMAIL

    low_concurrency = LeadGenInput(
        prompt="test",
        target_query="test",
        limit=4,
        max_concurrency=2,
    )

    async with Worker(
        env.client,
        task_queue="test-leads",
        workflows=[LeadGenerationWorkflow],
        workflow_runner=SANDBOXED_RUNNER,
        activities=[_search, _details, _qualify, _email],
    ):
        await env.client.execute_workflow(
            LeadGenerationWorkflow.run,
            low_concurrency,
            id="concurrency-wf",
            task_queue="test-leads",
        )

    if peak:
        assert max(peak) <= 2, f"Peak concurrency {max(peak)} exceeded limit of 2"
