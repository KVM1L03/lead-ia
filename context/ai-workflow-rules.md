# AI Workflow Rules

## Approach

This project uses a spec-driven workflow built on the `mattpocock-skills`
plugin (https://github.com/mattpocock/skills) — see root `AGENTS.md` §6 for
the full cycle. The `superpowers` plugin is not installed here; don't invoke
`superpowers:*` skills or reference them in new docs. For any change
touching more than one file:

0. Create the ticket's branch first — before any of the below.
1. Read `project-overview.md` → `architecture.md` → `ui-context.md`
   (frontend changes only) → `code-standards.md`, in that order.
2. Use `mattpocock-skills:domain-modeling` (and `mattpocock-skills:prototype`
   or `mattpocock-skills:grilling` where useful) to settle the approach — it
   writes/updates a design doc at
   `docs/specs/YYYY-MM-DD-<topic>-design.md`.
3. Once the approach is settled, write the implementation plan at
   `docs/plans/YYYY-MM-DD-<topic>.md`.
4. Execute the plan with `mattpocock-skills:tdd`.

Do not infer or invent behavior from scratch — always ground implementation
in these context files, `docs/roadmap.md`, and `docs/model-choices.md`.

## Scoping Rules

- Work on one feature unit at a time
- Prefer small, verifiable increments — PR target ≤200–400 LOC (root
  `AGENTS.md` §9 "Git workflow"); hard limit: backend diffs >400 lines
  skip the automated LLM review entirely
- Do not combine unrelated system boundaries (e.g. `maps_bridge` +
  `frontend`) in a single implementation step

## When to Split Work

Split an implementation step if it combines:

- Changes across more than one of `api_gateway/`, `maps_bridge/`,
  `ai_worker/`, `frontend/`
- A new Temporal activity/workflow change together with unrelated UI work
- Behavior not clearly defined in `project-overview.md` or
  `docs/roadmap.md`

If a change cannot be verified end to end quickly, the scope is too broad —
split it.

## Handling Missing Requirements

- Do not invent product behavior not defined in `project-overview.md`,
  `docs/roadmap.md`, or `docs/model-choices.md`
- If a requirement is ambiguous, resolve it in the relevant context file (or
  ask the user) before implementing
- If a requirement is missing, add it as an open question in
  `progress-tracker.md` before continuing

## Protected Files

Do not modify unless explicitly instructed:

- `frontend/app/generated/prisma/*` — gitignored, rebuilt by
  `prisma generate`
- Database migrations already applied
- `.github/prompts/llm-review-prompt.txt` — governs the automated PR review

## Keeping Docs in Sync

Update the relevant context file whenever implementation changes:

- System architecture or boundaries → `architecture.md`
- Storage model decisions → `architecture.md`
- Code conventions or standards → `code-standards.md`
- Product or feature scope → `project-overview.md`
- Visual design tokens → `ui-context.md`

## Before Moving to the Next Unit

1. The current unit works end to end within its defined scope
2. No invariant defined in root `AGENTS.md` was violated
3. `progress-tracker.md` reflects the completed work (or points at the new
   plan file that documents it)
4. `make lint && make test` passes (root `AGENTS.md` §7 "Commands")
