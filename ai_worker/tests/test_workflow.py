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
    ExpansionDecision,
    GeneratedEmail,
    Lead,
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

_EXPAND_DECISION = ExpansionDecision(
    target_query="dentist Krakow", strategy="city", axis_value="Krakow"
)


def _result(place_id: str) -> PlaceSearchResult:
    return _RESULT.model_copy(update={"id": place_id})


def _place(place_id: str) -> PlaceDetails:
    return _PLACE.model_copy(update={"id": place_id})


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
    async def mock_search(
        query: str,
        limit: int,
        maps_provider: str | None = None,
    ) -> list[PlaceSearchResult]:
        return [_RESULT] * n_places

    @activity.defn(name="get_place_details_activity")
    async def mock_details(
        place_id: str,
        maps_provider: str | None = None,
    ) -> PlaceDetails:
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

    @activity.defn(name="persist_phase_result_activity")
    async def mock_persist(
        run_id: str,
        status: str,
        scraped: int,
        qualified: int,
        emails_generated: int,
        leads: list[Lead],
        backfill_exhausted: bool = False,
        tried_cities: list[str] | None = None,
        tried_industries: list[str] | None = None,
    ) -> None:
        # Regression guard: a workflow call site passing fewer positional args than
        # this activity declares makes Temporal drop type hints and deliver dicts
        # instead of Lead instances (see ai_worker/workflows.py comment above the
        # "generating"-phase persist call).
        assert all(isinstance(lead, Lead) for lead in leads)

    @activity.defn(name="expand_search_query_activity")
    async def mock_expand(
        prompt: str,
        target_query: str,
        tried_cities: list[str],
        tried_industries: list[str],
        still_missing: int,
    ) -> ExpansionDecision:
        # mock_search always returns the same place id regardless of query, so any
        # backfill round this triggers dedupes to zero new results and stops itself.
        return _EXPAND_DECISION

    return [mock_search, mock_details, mock_qualify, mock_email, mock_persist, mock_expand]


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
    async def _search(
        query: str,
        limit: int,
        maps_provider: str | None = None,
    ) -> list[PlaceSearchResult]:
        return [_RESULT] * 4

    @activity.defn(name="get_place_details_activity")
    async def _details(
        place_id: str,
        maps_provider: str | None = None,
    ) -> PlaceDetails:
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

    @activity.defn(name="persist_phase_result_activity")
    async def _persist(
        run_id: str,
        status: str,
        scraped: int,
        qualified: int,
        emails_generated: int,
        leads: list[Lead],
        backfill_exhausted: bool = False,
        tried_cities: list[str] | None = None,
        tried_industries: list[str] | None = None,
    ) -> None:
        assert all(isinstance(lead, Lead) for lead in leads)

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
        activities=[_search, _details, _qualify, _email, _persist],
    ):
        await env.client.execute_workflow(
            LeadGenerationWorkflow.run,
            low_concurrency,
            id="concurrency-wf",
            task_queue="test-leads",
        )

    if peak:
        assert max(peak) <= 2, f"Peak concurrency {max(peak)} exceeded limit of 2"


# ── Backfill loop ──────────────────────────────────────────────────────────────


def _backfill_mocks(
    rounds: list[tuple[list[str], set[str]]],
    expand_tracker: list[tuple[list[str], list[str], int]],
    search_tracker: list[tuple[str, int]],
) -> list[Any]:
    """Mocks for an N-round backfill run. ``rounds[0]`` is the initial round-1 search
    result (ids, qualified-ids); ``rounds[1:]`` are consumed in order by each
    subsequent backfill-round search call, keyed by call index (not query text, since
    every round in a test may reuse the same decision)."""
    qualified_ids: set[str] = set()
    for _, round_qualified in rounds:
        qualified_ids |= round_qualified
    search_call_count = [0]

    @activity.defn(name="search_places_activity")
    async def mock_search(
        query: str,
        limit: int,
        maps_provider: str | None = None,
    ) -> list[PlaceSearchResult]:
        search_tracker.append((query, limit))
        idx = search_call_count[0]
        search_call_count[0] += 1
        ids = rounds[idx][0] if idx < len(rounds) else []
        return [_result(i) for i in ids]

    @activity.defn(name="get_place_details_activity")
    async def mock_details(
        place_id: str,
        maps_provider: str | None = None,
    ) -> PlaceDetails:
        return _place(place_id)

    @activity.defn(name="qualify_lead_activity")
    async def mock_qualify(outreach_goal: str, place: PlaceDetails) -> QualifierVerdict:
        return _VERDICT_GOOD if place.id in qualified_ids else _VERDICT_BAD

    @activity.defn(name="generate_email_activity")
    async def mock_email(
        outreach_goal: str,
        place: PlaceDetails,
        verdict: QualifierVerdict,
        sender_context: str,
    ) -> GeneratedEmail:
        return _EMAIL

    @activity.defn(name="persist_phase_result_activity")
    async def mock_persist(
        run_id: str,
        status: str,
        scraped: int,
        qualified: int,
        emails_generated: int,
        leads: list[Lead],
        backfill_exhausted: bool = False,
        tried_cities: list[str] | None = None,
        tried_industries: list[str] | None = None,
    ) -> None:
        assert all(isinstance(lead, Lead) for lead in leads)

    @activity.defn(name="expand_search_query_activity")
    async def mock_expand(
        prompt: str,
        target_query: str,
        tried_cities: list[str],
        tried_industries: list[str],
        still_missing: int,
    ) -> ExpansionDecision:
        expand_tracker.append((list(tried_cities), list(tried_industries), still_missing))
        return _EXPAND_DECISION

    return [mock_search, mock_details, mock_qualify, mock_email, mock_persist, mock_expand]


async def test_backfill_round_fills_shortfall_no_duplicates(env: WorkflowEnvironment) -> None:
    """Round 1: 5 places, 3 qualify (shortfall=2). Round 2 returns 1 duplicate + 2 new,
    both new leads qualify → shortfall closes, loop stops, no duplicate leads."""
    expand_tracker: list[tuple[list[str], list[str], int]] = []
    search_tracker: list[tuple[str, int]] = []
    mocks = _backfill_mocks(
        rounds=[
            (
                ["place-1", "place-2", "place-3", "place-4", "place-5"],
                {"place-1", "place-2", "place-3"},
            ),
            (["place-1", "place-6", "place-7"], {"place-6", "place-7"}),  # place-1 is a duplicate
        ],
        expand_tracker=expand_tracker,
        search_tracker=search_tracker,
    )

    async with Worker(
        env.client,
        task_queue="test-leads",
        workflows=[LeadGenerationWorkflow],
        workflow_runner=SANDBOXED_RUNNER,
        activities=mocks,
    ):
        result = await env.client.execute_workflow(
            LeadGenerationWorkflow.run,
            _INPUT,  # limit=5
            id="backfill-fills-shortfall-wf",
            task_queue="test-leads",
        )

    assert len(expand_tracker) == 1, "shortfall closed after round 1 — no second round needed"
    assert len(search_tracker) == 2
    lead_ids = [lead.place.id for lead in result.leads]
    assert len(lead_ids) == len(set(lead_ids)), "duplicate place-1 must not appear twice"
    assert len(result.leads) == 7  # 5 round-1 + 2 new round-2 (place-1 deduped away)
    qualified = [lead for lead in result.leads if lead.verdict and lead.verdict.is_qualified]
    assert len(qualified) == 5
    assert all(lead.email is not None for lead in qualified)
    assert result.backfill_exhausted is False, "shortfall closed — not exhausted"
    assert result.tried_cities == ["Krakow"]
    assert result.tried_industries == []


async def test_backfill_stops_on_no_progress(env: WorkflowEnvironment) -> None:
    """Round 1: 4 places, 2 qualify (shortfall=3). Round 2 yields 2 new leads, none
    qualify — loop must stop after round 1 even though shortfall is still open and
    the round cap (2) has not been reached."""
    expand_tracker: list[tuple[list[str], list[str], int]] = []
    search_tracker: list[tuple[str, int]] = []
    mocks = _backfill_mocks(
        rounds=[
            (["place-1", "place-2", "place-3", "place-4"], {"place-1", "place-2"}),
            (["place-5", "place-6"], set()),  # nobody in round 2 qualifies
        ],
        expand_tracker=expand_tracker,
        search_tracker=search_tracker,
    )

    async with Worker(
        env.client,
        task_queue="test-leads",
        workflows=[LeadGenerationWorkflow],
        workflow_runner=SANDBOXED_RUNNER,
        activities=mocks,
    ):
        result = await env.client.execute_workflow(
            LeadGenerationWorkflow.run,
            _INPUT,  # limit=5
            id="backfill-no-progress-wf",
            task_queue="test-leads",
        )

    assert len(expand_tracker) == 1, "must stop after the zero-progress round, not retry"
    qualified = [lead for lead in result.leads if lead.verdict and lead.verdict.is_qualified]
    assert len(qualified) == 2
    assert len(result.leads) == 6  # 4 round-1 + 2 new round-2 (unqualified)
    assert result.backfill_exhausted is True, "backfill tried but shortfall never closed"
    assert result.tried_cities == ["Krakow"]


async def test_backfill_stops_at_round_cap(env: WorkflowEnvironment) -> None:
    """Every round makes progress but never closes the shortfall — loop must stop
    after MAX_BACKFILL_ROUNDS (2), not continue indefinitely."""
    expand_tracker: list[tuple[list[str], list[str], int]] = []
    search_tracker: list[tuple[str, int]] = []
    mocks = _backfill_mocks(
        rounds=[
            (["place-1", "place-2", "place-3"], {"place-1", "place-2", "place-3"}),
            (["place-4", "place-5"], {"place-4", "place-5"}),  # round 2: progress, still short
            (["place-8", "place-9"], {"place-8", "place-9"}),  # round 3: progress, still short
        ],
        expand_tracker=expand_tracker,
        search_tracker=search_tracker,
    )

    high_limit = LeadGenInput(
        prompt=_INPUT.prompt,
        target_query=_INPUT.target_query,
        limit=10,
        sender_context=_INPUT.sender_context,
        max_concurrency=_INPUT.max_concurrency,
    )

    async with Worker(
        env.client,
        task_queue="test-leads",
        workflows=[LeadGenerationWorkflow],
        workflow_runner=SANDBOXED_RUNNER,
        activities=mocks,
    ):
        result = await env.client.execute_workflow(
            LeadGenerationWorkflow.run,
            high_limit,
            id="backfill-round-cap-wf",
            task_queue="test-leads",
        )

    assert len(expand_tracker) == 2, "must stop exactly at MAX_BACKFILL_ROUNDS"
    qualified = [lead for lead in result.leads if lead.verdict and lead.verdict.is_qualified]
    assert len(qualified) == 7  # 3 round-1 + 2 round-2 + 2 round-3, still short of limit=10
    assert result.backfill_exhausted is True, "round cap hit while still short of the limit"
    assert result.tried_cities == ["Krakow", "Krakow"]


async def test_backfill_never_triggered_when_round1_meets_limit(
    env: WorkflowEnvironment,
) -> None:
    """Round 1 alone meets the requested limit — expand_search_query_activity must
    never be called, and no extra search round runs."""
    expand_tracker: list[tuple[list[str], list[str], int]] = []
    search_tracker: list[tuple[str, int]] = []
    mocks = _backfill_mocks(
        rounds=[(["place-1", "place-2", "place-3"], {"place-1", "place-2", "place-3"})],
        expand_tracker=expand_tracker,
        search_tracker=search_tracker,
    )

    met_limit = LeadGenInput(
        prompt=_INPUT.prompt,
        target_query=_INPUT.target_query,
        limit=3,
        sender_context=_INPUT.sender_context,
        max_concurrency=_INPUT.max_concurrency,
    )

    async with Worker(
        env.client,
        task_queue="test-leads",
        workflows=[LeadGenerationWorkflow],
        workflow_runner=SANDBOXED_RUNNER,
        activities=mocks,
    ):
        result = await env.client.execute_workflow(
            LeadGenerationWorkflow.run,
            met_limit,
            id="backfill-not-triggered-wf",
            task_queue="test-leads",
        )

    assert expand_tracker == [], "expand_search_query_activity must never be called"
    assert len(search_tracker) == 1, "only the round-1 search must run"
    assert len(result.leads) == 3
    assert all(lead.verdict is not None and lead.verdict.is_qualified for lead in result.leads)
    assert result.backfill_exhausted is False, "backfill never engaged — nothing to report"
    assert result.tried_cities == []
    assert result.tried_industries == []


async def test_replay_safety_with_backfill_round(env: WorkflowEnvironment) -> None:
    """Run a workflow that exercises a Backfill round, capture history, replay —
    NondeterminismError must not be raised."""
    mocks = _backfill_mocks(
        rounds=[
            (
                ["place-1", "place-2", "place-3", "place-4", "place-5"],
                {"place-1", "place-2", "place-3"},
            ),
            (["place-6", "place-7"], {"place-6", "place-7"}),
        ],
        expand_tracker=[],
        search_tracker=[],
    )

    async with Worker(
        env.client,
        task_queue="test-leads",
        workflows=[LeadGenerationWorkflow],
        workflow_runner=SANDBOXED_RUNNER,
        activities=mocks,
    ):
        handle = await env.client.start_workflow(
            LeadGenerationWorkflow.run,
            _INPUT,  # limit=5
            id="replay-safety-backfill-wf",
            task_queue="test-leads",
        )
        await handle.result()
        history = await handle.fetch_history()

    replayer = Replayer(workflows=[LeadGenerationWorkflow], workflow_runner=SANDBOXED_RUNNER)
    await replayer.replay_workflow(history)
