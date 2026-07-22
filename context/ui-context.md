# UI Context

Source of truth: `frontend/app/globals.css`. If the two ever disagree, the
CSS file wins — update this doc to match, not the other way around.

## Theme

Light only — no dark mode. Warm near-white background with a subtle dual
radial-gradient wash (amber top-left, green bottom-right) behind everything,
a single warm amber accent color for brand/interactive elements, and a
glass-morphism surface treatment (translucent white + backdrop blur) for
floating panels: sidebar, drawers, cards, toolbars, modals. Serif for
display/headings (kept deliberately as a brand differentiator), sans for UI
text, mono for code and tabular data.

## Colors

All components must use these tokens (Tailwind v4 `@theme` in
`frontend/app/globals.css`) — no hardcoded hex values.

| Role | CSS Variable | Value |
|---|---|---|
| Page background | `--color-bg` / `--background` | `#f7f7f5` |
| Foreground / text | `--color-fg` / `--foreground` | `#1d1d1f` |
| Surface (cards) | `--color-surface` / `--card` | `#fcfcfa` |
| Glass surface (floating panels) | `--color-glass` | `rgba(255,255,255,.86)` |
| Glass surface (stronger) | `--color-glass-strong` | `rgba(255,255,255,.72)` |
| Glass border | `--color-glass-edge` | `rgba(10,10,10,.06)` |
| Muted text | `--color-muted-fg` / `--muted-foreground` | `#9b9ba1` |
| Subtle text | `--color-subtle` | `#6e6e73` |
| Brand / primary accent | `--color-brand` / `--primary` / `--ring` | `#c8742e` |
| Brand soft (hover, selection) | `--color-brand-soft` | `rgba(200, 116, 46, 0.1)` |
| Success / qualified | `--color-success` / `--color-success-fg` / `--color-success-soft` | `#2cb67d` / `#1f9d66` / `rgba(44,182,125,.12)` |
| Warning / borderline | `--color-warning` / `--color-warning-fg` / `--color-warning-soft` | `#f4a261` / `#b9790a` / `rgba(244,162,97,.2)` |
| Reject (soft destructive) | `--color-reject` / `--color-reject-soft` | `#e76f51` / `rgba(231,111,81,.06)` |
| Border | `--color-edge` / `--border` | `#e7e5dd` |
| Input border | `--color-edge-input` / `--input` | `#d6d3c9` |
| Skeleton / loading | `--color-skeleton` | `#efede6` |
| Secondary surface | `--secondary` / `--accent` | `#f0efe9` |
| Destructive (hard/severe actions, e.g. discard a run) | `--destructive` | `oklch(0.577 0.245 27.325)` |

`--color-reject` is the softer coral used for reversible actions (reject a
lead, close a drawer's danger state). `--destructive` (red) is reserved for
harder-to-undo actions like permanently deleting a run — see
`RunRow.tsx`'s discard-run confirmation dialog.

## Typography

| Role | Font | Variable |
|---|---|---|
| Headings / display | Source Serif 4 | `--font-serif` |
| UI / body text | Inter | `--font-sans` |
| Code / mono / tabular data | IBM Plex Mono | `--font-mono` |

## Border Radius

Base radius is `0.875rem` (`--radius`, 14px), scaled via `--radius-sm`
(×0.6 ≈ 8px) through `--radius-4xl` (×2.6 ≈ 36px). Use the Tailwind radius
utilities (`rounded-sm` … `rounded-4xl`) mapped to those variables — never
hardcode a pixel radius (e.g. `rounded-[3px]`).

| Context | Class |
|---|---|
| Inline / small UI (badges, chips) | `rounded-full` for pills, `rounded-md` for square-ish badges |
| Buttons, inputs | `rounded-xl` |
| Cards / toolbars / panels | `rounded-2xl` |
| Modals / drawers / large overlays | `rounded-3xl` or `rounded-4xl` |

## Glass Surfaces

Floating UI (sidebar, drawers, toolbars, modals, empty-state cards) uses a
translucent-white + backdrop-blur treatment rather than a flat opaque
surface: `bg-glass backdrop-blur-md` (or `backdrop-blur-xl`/`2xl` for larger
panels) plus `border border-glass-edge` and a soft shadow
(`shadow-[0_6px_24px_rgba(0,0,0,.04)]`-ish, scaled to the panel's size).
This only reads as "glass" because of the radial-gradient wash on `body` in
`globals.css` — don't remove that wash without also reconsidering every
`bg-glass` usage.

Not every surface should be glass: plain data tables, native `<dialog>`
confirmation modals (see `RunRow.tsx`), and small inline badges stay on the
opaque `--color-surface` / `--color-skeleton` tokens.

## Component Library

shadcn-style components via `@base-ui/react` on top of Tailwind v4.
Components live in `frontend/components/ui/`. Do not `npm install
@shadcn/ui` or `radix-ui` directly — see `frontend/AGENTS.md`. Note:
`ui/button.tsx` exists but is currently unused — every button in the app is
a hand-rolled `<button>` with inline Tailwind classes; adopting the shared
`Button` primitive is a separate refactor, not covered by styling passes.

## Layout Patterns

- **Approval UI**: `LeadCohortTable` renders leads as collapsible cohort
  groups (by score bucket × industry), not a flat card grid — expand a
  cohort to see its per-lead table rows. Responsive breakpoints
  (`sm:`/`md:`) are open work, see `docs/roadmap.md` #3.
- **Approval toolbar**: `FiltersBar` (score range, has-website, industry
  chips) plus header approve/export actions; mobile sticky bottom bar is
  open work, see `docs/roadmap.md` #3.
- **Email draft panel**: `EmailDrawer` — a right-side floating glass panel
  (inset from the viewport edges, not edge-to-edge), one per selected lead;
  collapsible-on-mobile is open work, see `docs/roadmap.md` #3.
- **Sidebar**: `Sidebar` floats as an inset glass panel (`left-3 top-3
  bottom-3`), not flush against the viewport edge. The main content
  column's left margin (`ml-[244px]` in `app/layout.tsx`) accounts for the
  sidebar's width plus its inset plus a visual gap — keep these in sync if
  the sidebar width or inset ever changes.

## Icons

Hand-rolled inline `<svg>`, stroke-based, no icon library. (`lucide-react`
is listed in `package.json` but is not currently imported anywhere — don't
assume it's wired up.) Observed stroke widths: `1.8`–`2.4`. Observed sizes:
`h-3 w-3` for compact/badge contexts, `h-4 w-4` for standard inline icons,
`h-8 w-8` for larger standalone icons. Prefer `h-4 w-4` as the default
unless a specific context calls for another size already in use.
