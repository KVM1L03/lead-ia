# Progress Tracker

Update this file after every meaningful implementation change. This is a
rolling index into `docs/plans/`, not a full duplicate log —
when a new plan lands, add one row to Completed; don't re-narrate its
contents here.

## Current Phase

In progress — near-term roadmap items (`docs/roadmap.md`): Terraform/infra
validation (#1) and Gemini migration behind an eval gate (#2, blocked on the
DSPy-path qualifier eval).

## Current Goal

Site Profile, Contact Ledger and Preflight — closing the four product gaps
that stop a run from being actionable and a second run from being safe. See
`docs/specs/2026-09-16-site-profile-ledger-preflight-design.md`
and ADRs 0003–0005; twelve tickets tracked on GitHub.

## Completed

Full dated history lives in `docs/plans/`. Most recent:

| Date | Plan | Summary |
|---|---|---|
| 2026-09-16 | deepen-export-graph-injection | Issue #86: CSV export collapsed onto `POST /api/leads/export`; `build_lead_state` + `should_generate_email` shared by both orchestrators; provider/LM resolved at entry points and injected (no `frontend/lib/csv.ts`, no `get_provider` settings-vs-active bug) |
| 2026-08-05 | exhaustion-banner-review-ui | `LeadCohortTable` renders a non-alarming exhaustion banner (`ExhaustionBanner` + pure `buildExhaustionBannerText` in `lib/exhaustionBanner.ts`) sourced from the Prisma `Run` row's `backfillExhausted`/`triedCities`/`triedIndustries`, nothing renders when absent — Backfill 4/4 (issue #76, part of epic #72), `.scratch/backfill/issues/04-exhaustion-banner-review-ui.md`, PR pending |
| 2026-08-05 | persist-exhaustion-result-status-api | `RunRow` gains `backfill_exhausted`/`tried_cities`/`tried_industries` (SQLAlchemy DDL + Prisma mirror), `LeadGenOutput` and `persist_phase_result_activity` carry them through, `GET /api/leads/status/{id}` returns them — Backfill 3/4 (issue #75, part of epic #72), `.scratch/backfill/issues/03-persist-exhaustion-result-status-api.md`, PR #80 merged |
| 2026-08-04 | wire-backfill-loop-into-workflow | Backfill round loop wired into `LeadGenerationWorkflow.run()`, between qualify and email — Backfill 2/4 (issue #74, part of epic #72), `.scratch/backfill/issues/02-wire-backfill-loop-into-workflow.md`, PR #79 merged |
| 2026-08-04 | expand-search-query-decision-engine | `ExpandSearchQuery` DSPy signature + Temporal activity — Backfill 1/4 (issue #73, part of epic #72), PR #77 merged |
| 2026-07-11 | maps-pagination | SerpAPI/Places pagination support |
| 2026-07-10 | mock-provider-recorded-fixtures | Recorded fixtures for the mock maps provider |
| 2026-07-10 | optional-rating | Optional rating field on the `google_places` path |
| 2026-07-10 | google-places-provider | `GooglePlacesProvider` (`MAPS_PROVIDER=google_places`) |
| 2026-07-07 | csv-export / csv-export-ui | CSV export of approved leads |
| 2026-07-06 | langgraph-hot-path | LangGraph wired on sync + Temporal paths |
| 2026-07-05 | demo-mode-sync-pipeline | `EXECUTION_MODE=sync` Cloud Run demo path |
| 2026-07-03 | demo-rate-limiting | Rate limiting for the public demo |

## In Progress

- Site Profile / Contact Ledger / Preflight — design approved, tickets 1–12
  queued (see Current Goal)

## Next Up

- Terraform modules validation + deploy runbook (`docs/roadmap.md` #1)
- DSPy-path qualifier eval → Gemini migration gate (`docs/roadmap.md` #2)
- Frontend responsive layout (`docs/roadmap.md` #3)

## Open Questions

- Gemini vs. Haiku on the DSPy-path qualifier eval — not yet run; migration
  is blocked until it is (`docs/model-choices.md` § Migration plan)
- Langfuse self-hosted (small GCE VM) vs. Langfuse Cloud — cost vs.
  data-residency tradeoff, undecided (`docs/roadmap.md` #1)

## Architecture Decisions

- Two-model split (Haiku qualify / Sonnet email) — driven by eval results,
  see README "Engineering decisions"
- Sync path bypasses Temporal for the public demo to avoid an always-on
  Cloud Run instance (~$30/month) — see README
- A shared `orchestrate()` abstraction across the sync/Temporal paths was
  considered and rejected as a leaky abstraction over two genuinely
  different execution models — see README

## Session Notes

- 2026-09-22: Resolved the `superpowers` vs. `mattpocock-skills` mismatch
  flagged below — root `AGENTS.md` §6 now documents the `mattpocock-skills`
  workflow (the plugin actually installed in this environment) instead of
  `superpowers`, `docs/superpowers/{specs,plans}/` were renamed to
  `docs/specs/` and `docs/plans/`, and `CLAUDE.md` was slimmed to a one-line
  `@AGENTS.md` pointer so there is one canonical instruction file. See PR for
  `chore/consolidate-agent-instructions`.
- (Historical, now resolved above) The `superpowers` Claude Code plugin
  referenced by the old root `CLAUDE.md` §2 (the `brainstorming` /
  `writing-plans` skills, `docs/superpowers/specs/` and
  `docs/superpowers/plans/`) was never installed in this environment — only
  `mattpocock-skills` was present under `~/.claude/plugins`. Backfill 1/4
  (issue #73) also shipped with no spec/plan doc under `docs/superpowers/`,
  confirming that step was skipped in practice, not just one session.
  Backfill 2/4 (issue #74) proceeded straight from the ticket file + ADRs to
  implementation on a feature branch, following that precedent.
