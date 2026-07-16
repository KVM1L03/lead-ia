# AI Workflow Rules

## Approach

This project uses a spec-driven workflow built on the Superpowers Claude
Code plugin. For any change touching more than one file:

1. Read `project-overview.md` → `architecture.md` → `ui-context.md`
   (frontend changes only) → `code-standards.md`, in that order.
2. Invoke the `superpowers:brainstorming` skill — it explores intent,
   requirements, and 2-3 candidate approaches through dialogue, then writes
   a design doc to `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md`.
3. Once the spec is approved, invoke `superpowers:writing-plans` to produce
   an implementation plan in `docs/superpowers/plans/YYYY-MM-DD-<topic>.md`.
4. Execute the plan.

Do not infer or invent behavior from scratch — always ground implementation
in these context files, `docs/roadmap.md`, and `docs/model-choices.md`.

## Scoping Rules

- Work on one feature unit at a time
- Prefer small, verifiable increments — PR target ≤200–400 LOC (root
  `CLAUDE.md` §5 "Workflow rules"); hard limit: backend diffs >400 lines
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
4. `make lint && make test` passes (root `CLAUDE.md` §3 "Commands")
