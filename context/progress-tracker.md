# Progress Tracker

Update this file after every meaningful implementation change. This is a
rolling index into `docs/superpowers/plans/`, not a full duplicate log —
when a new plan lands, add one row to Completed; don't re-narrate its
contents here.

## Current Phase

In progress — near-term roadmap items (`docs/roadmap.md`): Terraform/infra
validation (#1) and Gemini migration behind an eval gate (#2, blocked on the
DSPy-path qualifier eval).

## Current Goal

Merging the `context/` spec template into the existing Superpowers
spec-driven workflow — see
`docs/superpowers/specs/2026-07-16-context-driven-spec-workflow-design.md`.

## Completed

Full dated history lives in `docs/superpowers/plans/`. Most recent:

| Date | Plan | Summary |
|---|---|---|
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
  doc system (this task)

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

- None — start of the spec-driven doc merge work.
