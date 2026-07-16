# UI Context

Source of truth: `frontend/app/globals.css`. If the two ever disagree, the
CSS file wins — update this doc to match, not the other way around.

## Theme

Light only — no dark mode. Monochrome base (near-white background, near-black
text) with a single warm amber accent color for brand/interactive elements.
Editorial, restrained visual language: serif for display/headings, sans for
UI text, mono for code and tabular data.

## Colors

All components must use these tokens (Tailwind v4 `@theme` in
`frontend/app/globals.css`) — no hardcoded hex values.

| Role | CSS Variable | Value |
|---|---|---|
| Page background | `--color-bg` / `--background` | `#fafaf7` |
| Foreground / text | `--color-fg` / `--foreground` | `#0a0a0a` |
| Surface (cards) | `--color-surface` / `--card` | `#fcfcfa` |
| Muted text | `--color-muted-fg` / `--muted-foreground` | `#a6a49b` |
| Subtle text | `--color-subtle` | `#6a6a62` |
| Brand / primary accent | `--color-brand` / `--primary` / `--ring` | `#c8742e` |
| Brand soft (hover, selection) | `--color-brand-soft` | `rgba(200, 116, 46, 0.1)` |
| Border | `--color-edge` / `--border` | `#e7e5dd` |
| Input border | `--color-edge-input` / `--input` | `#d6d3c9` |
| Skeleton / loading | `--color-skeleton` | `#efede6` |
| Secondary surface | `--secondary` / `--accent` | `#f0efe9` |
| Destructive | `--destructive` | `oklch(0.577 0.245 27.325)` |

## Typography

| Role | Font | Variable |
|---|---|---|
| Headings / display | Source Serif 4 | `--font-serif` |
| UI / body text | Inter | `--font-sans` |
| Code / mono / tabular data | IBM Plex Mono | `--font-mono` |

## Border Radius

Base radius is `0.1875rem` (`--radius`), scaled via `--radius-sm` (×0.6)
through `--radius-4xl` (×2.6). Use the Tailwind radius utilities
(`rounded-sm` … `rounded-4xl`) mapped to those variables — never hardcode a
pixel radius.

| Context | Class |
|---|---|
| Inline / small UI (badges, chips) | `rounded-sm` / `rounded-md` |
| Cards / panels | `rounded-lg` |
| Modals / overlays | `rounded-xl` or larger |

## Component Library

shadcn-style components via `@base-ui/react` on top of Tailwind v4.
Components live in `frontend/components/ui/`. Do not `npm install
@shadcn/ui` or `radix-ui` directly — see `frontend/AGENTS.md`.

## Layout Patterns

- **Approval UI**: lead card grid, currently fixed-width columns — responsive
  breakpoints (`sm:`/`md:`) are open work, see `docs/roadmap.md` #3
- **Approval toolbar**: approve/reject actions per lead card; mobile sticky
  bottom bar is open work, see `docs/roadmap.md` #3
- **Email draft panel**: rendered per lead card; collapsible-on-mobile is
  open work, see `docs/roadmap.md` #3

## Icons

Lucide React (`lucide-react`), stroke-based icons only. Observed sizes in
this codebase: `h-3 w-3` for compact/badge contexts, `h-4 w-4` for standard
inline icons, `h-8 w-8` for larger standalone icons. Prefer `h-4 w-4` as the
default unless a specific context calls for another size already in use.
