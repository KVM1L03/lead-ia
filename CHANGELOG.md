# Changelog

All notable changes to LeadIA. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning is [SemVer](https://semver.org/) on a `0.x` line — the public surface is the pipeline and the
approval UI, not a library API.

Each release links the pull requests that shipped it. Git tags and GitHub Releases are not cut yet — this
file is the release history, and version-to-version compare links land with the first tag.

---

## [Unreleased]

### Removed
- The automated LLM diff review CI workflow (`llm-review.yml`) — low signal relative to the
  review time it cost, and occasionally misjudged a diff. PRs now rely on `python`/`frontend`
  CI plus human review only. See [ADR 0007](docs/adr/0007-remove-automated-llm-diff-review.md).

### Changed
- The qualifier's yes/no decision now comes from TypeSafe Jev (`jev-1.13.0`), not Haiku;
  Haiku 4.5 is only called, on leads Jev passes, to write the one-sentence reasoning shown
  in the email draft and CSV export. `icp_fit` is always empty (decomposition is #99). See
  [ADR 0006](docs/adr/0006-jev-for-qualification-decision.md)
  ([#106](https://github.com/KVM1L03/lead-ia/pull/106)).
- Approve-and-export and Export CSV both serialize through `POST /api/leads/export`; the
  duplicated client-side CSV builder is gone ([#87](https://github.com/KVM1L03/lead-ia/pull/87)).
- New LeadIA logo and favicon; README restructured into a short overview with a banner, with engineering
  decisions, evaluation, and deployment notes moved to `docs/engineering-decisions.md` ([#85](https://github.com/KVM1L03/lead-ia/pull/85)).
- README rewritten: shorter narrative, system + agent-flow diagrams, engineering decisions collapsed into
  scannable sections, release history surfaced ([#84](https://github.com/KVM1L03/lead-ia/pull/84)).

### Added
- This changelog ([#84](https://github.com/KVM1L03/lead-ia/pull/84)).

### Planned
See [`docs/roadmap.md`](./docs/roadmap.md) — Terraform validation + deploy runbook, the Gemini migration
behind its eval gate, and a responsive approval UI.

---

## [0.8.0] — 2026-08-05

**Backfill** — the pipeline no longer under-delivers in silence. When qualification leaves a cohort short of
the requested limit, an LLM decides which axis to widen and the search re-runs.

### Added
- `ExpandSearchQuery` DSPy signature + Temporal activity: picks a strategy axis (`city` or `industry`),
  emits the next Maps query, and never retries an axis value already tried ([#77](https://github.com/KVM1L03/lead-ia/pull/77)).
- Backfill round loop wired into `LeadGenerationWorkflow`, between qualify and email — bounded by
  `MAX_BACKFILL_ROUNDS = 2` plus a no-progress early exit ([#79](https://github.com/KVM1L03/lead-ia/pull/79)).
- Exhaustion state persisted (`backfillExhausted`, `triedCities`, `triedIndustries`) and exposed via
  `GET /api/leads/status/{id}` ([#80](https://github.com/KVM1L03/lead-ia/pull/80)).
- Non-alarming exhaustion banner in the review UI, rendered only when the run actually ran out of room
  ([#81](https://github.com/KVM1L03/lead-ia/pull/81)).
- ADRs [0001](./docs/adr/0001-backfill-temporal-only.md) (Backfill is Temporal-only) and
  [0002](./docs/adr/0002-backfill-single-final-email-pass.md) (one final email pass over the merged pool).

### Fixed
- `persist_phase_result_activity` was invoked with fewer positional args than its signature declares —
  Temporal then decoded every argument as an untyped dict, crashing every real Temporal run
  ([#82](https://github.com/KVM1L03/lead-ia/pull/82)).
- Backfill rounds on the city axis reused the original outreach goal too narrowly, so widened searches
  qualified against the wrong ICP ([#83](https://github.com/KVM1L03/lead-ia/pull/83)).

---

## [0.7.0] — 2026-07-29

### Added
- Glass-morphism restyle of the LeadForge design system across the app shell and review UI
  ([#70](https://github.com/KVM1L03/lead-ia/pull/70)).
- Demo prompt examples that are known to hit recorded fixtures — no more guessing what to type
  ([#71](https://github.com/KVM1L03/lead-ia/pull/71)).
- Spec-driven development workflow — the agent-facing "constitution" under `context/`, with plans and specs
  in `docs/superpowers/` ([#69](https://github.com/KVM1L03/lead-ia/pull/69)).

### Fixed
- Pipeline no longer blocks the event loop on DSPy calls, and MCP sessions are reused across a run instead
  of reconnecting per lead ([#68](https://github.com/KVM1L03/lead-ia/pull/68)).

---

## [0.6.0] — 2026-07-11

Cost engineering release: a second live Maps provider with a 20× larger free tier, and a demo that costs $0
to serve.

### Added
- `GooglePlacesProvider` (`MAPS_PROVIDER=google_places`) — Places API (New) Text Search + Place Details,
  5 000 free calls/month ([#57](https://github.com/KVM1L03/lead-ia/pull/57)).
- FieldMask cost invariant: the request omits every rating/review field to stay on the Pro SKU tier, asserted
  by tests. Documented in [`docs/cost-guardrails.md`](./docs/cost-guardrails.md)
  ([#56](https://github.com/KVM1L03/lead-ia/pull/56), [#59](https://github.com/KVM1L03/lead-ia/pull/59)).
- Maps provider selectable from the UI and threaded through the whole pipeline
  ([#58](https://github.com/KVM1L03/lead-ia/pull/58)).
- Fixture recording script + recorded-fixture mock provider with exact-token, Jaccard-fuzzy and round-robin
  matching — the basis of the zero-cost live demo
  ([#60](https://github.com/KVM1L03/lead-ia/pull/60), [#61](https://github.com/KVM1L03/lead-ia/pull/61)).
- Maps search pagination ([#67](https://github.com/KVM1L03/lead-ia/pull/67)).

### Changed
- `rating` / `review_count` are now optional and `None` on the `google_places` path; every consumer drops
  them via `exclude_none=True` before the prompt ([#56](https://github.com/KVM1L03/lead-ia/pull/56)).
- Demo mode forces the mock provider regardless of configuration ([#62](https://github.com/KVM1L03/lead-ia/pull/62)).

### Fixed
- Approval 404'd in demo mode because persistence is disabled — the DB write is now skipped
  ([#65](https://github.com/KVM1L03/lead-ia/pull/65)).
- CSV export generated in a Server Action instead of an HTTP round-trip through the API
  ([#66](https://github.com/KVM1L03/lead-ia/pull/66)).

---

## [0.5.0] — 2026-07-08

The project goes public: a synchronous execution path that runs on scale-to-zero infrastructure.

### Added
- `EXECUTION_MODE=sync` — the full pipeline on the FastAPI request thread, hard-capped at 25 leads, for the
  Cloud Run demo ([#40](https://github.com/KVM1L03/lead-ia/pull/40)).
- CSV export of approved leads — business data, drafted email, qualification metadata — end to end
  ([#52](https://github.com/KVM1L03/lead-ia/pull/52), [#53](https://github.com/KVM1L03/lead-ia/pull/53)).
- `make eval-dspy` — eval harness that runs the *production* `qualify_lead()` through its DSPy signature,
  rather than a proxy prompt. Haiku scores F1 83% vs 78% on the proxy
  ([#55](https://github.com/KVM1L03/lead-ia/pull/55)).

### Changed
- LangGraph moved onto both hot paths; Temporal activities became thin wrappers over the same graph nodes
  ([#47](https://github.com/KVM1L03/lead-ia/pull/47)).
- The deliberate two-orchestration-path design documented with cross-references instead of being refactored
  into a leaky shared abstraction ([#49](https://github.com/KVM1L03/lead-ia/pull/49)).

### Removed
- `LLM_PROVIDER` env var — never read by production code; LLM mocking is test-level
  ([#50](https://github.com/KVM1L03/lead-ia/pull/50)).

---

## [0.4.0] — 2026-07-03

### Added
- Promptfoo eval suite with a 100-example hand-labeled qualifier gold set (50 qualified, 30 hard negatives,
  20 ambiguous) and a metrics report ([#34](https://github.com/KVM1L03/lead-ia/pull/34)).
- Two-layer demo rate limiting: global daily run cap (Redis Lua INCR + EXPIRE, or in-process) and per-IP
  per-minute middleware ([#37](https://github.com/KVM1L03/lead-ia/pull/37)).
- Multi-stage Cloud Run Dockerfiles + twelve-factor fixes ([#38](https://github.com/KVM1L03/lead-ia/pull/38)).
- Terraform bootstrap — VPC, Artifact Registry, API enablement ([#39](https://github.com/KVM1L03/lead-ia/pull/39)).

---

## [0.3.0] — 2026-07-02

The human-in-the-loop surface: everything a reviewer needs to approve, edit, or reject a cohort.

### Added
- Prisma 7 data layer — schema, client singleton, read path ([#24](https://github.com/KVM1L03/lead-ia/pull/24)).
- LeadForge design system + app shell ([#25](https://github.com/KVM1L03/lead-ia/pull/25)).
- Run progress view — three pipeline stages with a live tail ([#28](https://github.com/KVM1L03/lead-ia/pull/28)).
- `LeadCohortTable` + `EmailDrawer` for review ([#29](https://github.com/KVM1L03/lead-ia/pull/29)).
- Run history page with delete and approval stats ([#30](https://github.com/KVM1L03/lead-ia/pull/30)).
- Lead search form ([#31](https://github.com/KVM1L03/lead-ia/pull/31)).

### Fixed
- LLM router deadlock and a `dspy.BaseLM` incompatibility ([#27](https://github.com/KVM1L03/lead-ia/pull/27)).
- Browser CORS on status polling, resolved with a Next.js proxy route
  ([#32](https://github.com/KVM1L03/lead-ia/pull/32)).

---

## [0.2.0] — 2026-07-01

The pipeline becomes durable and reachable over HTTP.

### Added
- LangGraph per-lead agent graph: `qualify → decide → email` ([#15](https://github.com/KVM1L03/lead-ia/pull/15)).
- Temporal activities (search, qualify, email) with per-step timeouts, typed retry policies and
  non-retryable exception lists ([#16](https://github.com/KVM1L03/lead-ia/pull/16)).
- `LeadGenerationWorkflow` — durable orchestration with partial results via `@workflow.query`
  ([#17](https://github.com/KVM1L03/lead-ia/pull/17)).
- Langfuse observability — OTel spans for every LLM call, correlated across activity boundaries by
  `SHA-256(workflow_id)` ([#18](https://github.com/KVM1L03/lead-ia/pull/18)).
- REST surface: `POST /api/leads/search`, `GET /api/leads/status`, `POST /api/leads/approve`
  ([#19](https://github.com/KVM1L03/lead-ia/pull/19), [#20](https://github.com/KVM1L03/lead-ia/pull/20),
  [#21](https://github.com/KVM1L03/lead-ia/pull/21)).
- Multi-provider LLM router with a per-role fallback chain ([#13](https://github.com/KVM1L03/lead-ia/pull/13)).
- PolyForm Noncommercial license ([#22](https://github.com/KVM1L03/lead-ia/pull/22)).

---

## [0.1.0] — 2026-06-30

Foundations — the tool boundary and the typed LLM programs everything else is built on.

### Added
- Python + Next.js monorepo skeleton, Dockerfiles, Docker Compose, `Makefile`.
- CI from day one: ruff, mypy, pytest, eslint, tsc, vitest, plus an advisory LLM diff review
  ([#3](https://github.com/KVM1L03/lead-ia/pull/3), [#14](https://github.com/KVM1L03/lead-ia/pull/14)).
- Temporal + Langfuse local stacks ([#5](https://github.com/KVM1L03/lead-ia/pull/5)).
- `maps_bridge` MCP server with an abstract `MapsProvider` boundary — the only process allowed to call
  SerpAPI ([#6](https://github.com/KVM1L03/lead-ia/pull/6)).
- `MockMapsProvider` with fixture data for local dev, CI and evals ([#7](https://github.com/KVM1L03/lead-ia/pull/7)).
- SerpAPI provider, 24 h SQLite cache, cassette-based tests ([#8](https://github.com/KVM1L03/lead-ia/pull/8)).
- Shared Pydantic wire schemas — `QualifierVerdict`, `GeneratedEmail` et al., consumed by every service
  ([#10](https://github.com/KVM1L03/lead-ia/pull/10)).
- `QualifyLead` DSPy signature — typed qualification, no raw prompt strings
  ([#11](https://github.com/KVM1L03/lead-ia/pull/11)).
- `GenerateEmail` DSPy signature — subject and body constrained at the type level
  ([#12](https://github.com/KVM1L03/lead-ia/pull/12)).
