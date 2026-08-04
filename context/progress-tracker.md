# Progress Tracker

Update this file after every meaningful implementation change. This is a
rolling index into recent work (GitHub issues, PRs, ADRs), not a full
duplicate log — when a unit of work lands, add one row to Completed; don't
re-narrate its contents here.

## Current Phase

In progress — near-term roadmap items (`docs/roadmap.md`): Terraform/infra
validation (#1) and Gemini migration behind an eval gate (#2, blocked on the
DSPy-path qualifier eval).

## Current Goal

Backfill epic (#72): reactive search-expansion loop for lead generation —
see `.scratch/backfill/issues/` and `docs/adr/0001-backfill-temporal-only.md`,
`docs/adr/0002-backfill-single-final-email-pass.md`.

## Completed

Full dated history lives in git log / merged PRs. Most recent:

| Date | Plan | Summary |
|---|---|---|
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

- Root `AGENTS.md` / `CLAUDE.md` restructuring to complete the spec-driven
  doc system — the Superpowers plugin references are dropped (this task);
  `CONTEXT.md` + `docs/adr/` + `docs/agents/` domain-doc restructuring is
  still uncommitted, separate task
- Backfill 2/4: wire the `ExpandSearchQuery` round loop into
  `LeadGenerationWorkflow` (`.scratch/backfill/issues/02-wire-backfill-loop-into-workflow.md`,
  issue #74, part of epic #72) — PR #79 open, awaiting CI + review

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

- The `superpowers` Claude Code plugin (previously referenced by root
  `CLAUDE.md` §2 and `context/ai-workflow-rules.md` for
  `brainstorming`/`writing-plans` and the `docs/superpowers/specs/` +
  `docs/superpowers/plans/` doc pipeline) was never actually installed in
  this environment — only `mattpocock-skills` is. Both `CLAUDE.md` and
  `context/ai-workflow-rules.md` now describe the spec-driven workflow
  without depending on it, pointing at `mattpocock-skills:domain-modeling`
  / `mattpocock-skills:prototype` for design work instead. Existing docs
  under `docs/superpowers/` (already-merged historical specs/plans) are left
  as-is — only the forward-looking process description changed.
