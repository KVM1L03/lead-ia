# Design: Merge `context/` spec template into the existing Superpowers workflow

Date: 2026-07-16

## Background

The user added a `context/` folder (generic spec-driven-development template:
`project-overview.md`, `architecture.md`, `ui-context.md`, `code-standards.md`,
`ai-workflow-rules.md`, `progress-tracker.md`) sourced from a template author's
CLAUDE.md snippet, and asked to (a) research current Claude Code spec-driven
development best practices, (b) fill in `context/` for this project, (c) edit
root `CLAUDE.md` and create `AGENTS.md` so everything forms one coherent system.

Discovery: this repo already runs an active spec-driven workflow via the
Superpowers plugin (`docs/superpowers/plans/` has 9 real feature plans dated
2026-07-03 through 2026-07-11, produced by the same brainstorming →
writing-plans → executing-plans skill chain used for this design). The
`context/` template is a lighter, generic version of the same underlying idea,
written for a Next.js/Clerk SaaS that doesn't match this project's actual
stack (Python/FastAPI/Temporal/DSPy backend, no auth, BYOK).

## Research findings

- Anthropic and community best practice treats `CLAUDE.md` as the project
  "constitution" and recommends keeping it short — accuracy on long instruction
  files degrades (some reports show 95%→60% past a length threshold), so
  shorter and more focused beats comprehensive-but-bloated.
  ([Claude Code Docs](https://code.claude.com/docs/en/best-practices),
  [CLAUDE.md Best Practices 2026](https://dev.to/nishilbhave/claudemd-best-practices-the-complete-2026-guide-435j))
- `AGENTS.md` is the emerging cross-tool standard (OpenAI, Google, Cursor);
  `CLAUDE.md` is Claude Code's native file and commonly imports `AGENTS.md`
  via `@AGENTS.md` for shared, tool-agnostic content — which is exactly the
  pattern already in use in `frontend/CLAUDE.md` + `frontend/AGENTS.md` in
  this repo.
- "Lazy loading": keep the root instruction file lean and push detail into
  files that get pulled in on demand (nested/linked instruction files read
  when relevant), rather than one large file holding everything.
- Senior-engineer pattern: CLAUDE.md/AGENTS.md hold durable, rarely-changing
  facts (constitution); per-feature specs and plans are separate, dated,
  disposable documents — which is precisely what `docs/superpowers/specs/`
  and `docs/superpowers/plans/` already are in this repo.

Conclusion: don't build a third, parallel spec system. Fold `context/` into
the existing two-layer pattern (`AGENTS.md` = facts, `CLAUDE.md` = process)
this repo already validated in `frontend/`, and make `context/` the
"constitution" that Superpowers' brainstorming skill reads before writing
each new spec. `docs/superpowers/{specs,plans}/` remains the per-feature
layer, untouched.

## Decisions (confirmed with user)

1. **Merge, don't replace or run in parallel.** `context/*.md` becomes durable
   reference content; per-feature tracking stays in `docs/superpowers/specs`
   and `plans` — `progress-tracker.md` becomes a short rolling index into
   those, not a duplicate log.
2. **Mirror the `frontend/` AGENTS.md/CLAUDE.md split at the root.** Create
   root `AGENTS.md` (tool-agnostic facts). Slim root `CLAUDE.md` to
   `@AGENTS.md` import + Claude-Code-specific process, with a new pointer to
   `context/` and to the Superpowers skill chain.

## File-by-file plan

### `AGENTS.md` (new, root)
Moved verbatim from current `CLAUDE.md`: stack table (§2), repo layout (§3),
architecture invariants 1-6 (§4), anti-patterns (§11), env var table (§6).

### `CLAUDE.md` (root, slimmed)
`@AGENTS.md` import at top. Keeps: what this is/isn't (§1), commands (§5),
testing (§7), git/PR workflow (§8), CI pipeline (§9), "when confused"
pointers (§10). Drops the content now owned by `AGENTS.md`. Adds one new
section: read `context/*.md` in order, then use
`superpowers:brainstorming` → `writing-plans` → `executing-plans` for
anything touching >1 file; specs land in `docs/superpowers/specs/`, plans in
`docs/superpowers/plans/`.

### `context/project-overview.md`
Filled from README "The problem" / "What it does" + `docs/roadmap.md` §5
(out of scope: auth, billing, email sending, multi-tenant — matches
CLAUDE.md §1 IS/IS NOT). Success criteria from README + roadmap near-term
items 1-4.

### `context/architecture.md`
Stack/boundaries **link to `AGENTS.md`** rather than repeat it. Adds what
AGENTS.md doesn't cover: two-orchestration-path narrative (Temporal vs sync,
from README "Engineering decisions"), storage model (Postgres `app` schema +
SQLite SerpAPI cache), auth model (none — BYOK by design).

### `context/ui-context.md`
Real tokens from `frontend/app/globals.css`: light theme (not dark — the
generic template assumed dark), monochrome + amber accent (`#c8742e`), fonts
(Source Serif / Inter / IBM Plex Mono), radius scale (`0.1875rem` base),
shadcn via `@base-ui/react`.

### `context/code-standards.md`
Points to `AGENTS.md` + `frontend/AGENTS.md` for cross-cutting/TS rules;
adds Python-specific standards not documented elsewhere: Pydantic v2 strict,
DSPy typed signatures (no raw prompts), ruff/mypy as source of truth.

### `context/ai-workflow-rules.md`
Rewritten around the actual Superpowers cycle: brainstorming → writing-plans
→ executing-plans; PR size limits (≤200-400 LOC, hard 400-line LLM-review
ceiling); protected files (generated Prisma client, migrations); "don't
invent behavior — check `docs/roadmap.md` / `docs/model-choices.md` first."

### `context/progress-tracker.md`
Short rolling index: Current Phase (roadmap items 1-2: Terraform +
Gemini migration), table of the 9 existing plans in
`docs/superpowers/plans/` with one-line status each, Open Questions from
roadmap's blocked items (Gemini eval gate).

## Out of scope

- No changes to `frontend/CLAUDE.md` / `frontend/AGENTS.md` — already correct.
- No new tooling, no CI changes, no automation to enforce the read-order —
  this is documentation-only.
