# LeadForge Glass Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Per established user preference, execute tasks inline (no per-task subagent review loop) — see `execution-style-lean` memory.

**Goal:** Restyle the existing LeadIA frontend (Sidebar, Topbar, empty state, search form, cohort review table, email drawer, run-progress views, history) to match the visual language of the imported Claude Design mockup (`https://claude.ai/design/p/712f7e2a-b406-4d6e-a5e7-aa4d2ee98557?file=LeadForge.dc.html`) — glass-morphism cards, larger border radii, a status color system (qualified/borderline/rejected), and a subtle background wash — **without** building any new screens, components, or features.

**Architecture:** Pure visual-token + className changes. Add new CSS custom properties to `frontend/app/globals.css` (`@theme` block), raise the shared `--radius` base so the existing `rounded-sm…rounded-4xl` scale produces the mockup's card/button proportions, then walk each existing component replacing hardcoded `rounded-[3px]` / raw Tailwind palette classes (`emerald-700`, `amber-50`, etc.) with the new token-driven utilities. No new files, no new components, no behavior changes — existing Vitest suites must stay green throughout.

**Tech Stack:** Next.js 16 (Turbopack), Tailwind v4 (CSS-first `@theme`, no config file), TypeScript strict, Vitest.

## Global Constraints

- No `tailwind.config.js` — all tokens live in `frontend/app/globals.css` `@theme` / `:root` blocks (`frontend/AGENTS.md`).
- No hardcoded hex values in components — every color must resolve through a `--color-*` token (`context/ui-context.md`).
- Keep serif (`font-serif` / Source Serif 4) on all headings/display text — confirmed with user, do NOT switch to Inter-only despite the mockup being Inter-only.
- Do not build: the "Feed" screen, saved-searches list in the sidebar, the "Plan Growth"/credits meter, the ICP-chips editor, the geographic-radius slider, or the two non-"first-time" empty-state variants (segment-exhausted / zero-qualified) — none of these concepts exist in the current product (`context/project-overview.md` explicitly scopes them out). Restyle only surfaces that already exist.
- Do not swap the icon system to `lucide-react` — despite `context/ui-context.md` claiming Lucide is used, the actual codebase is 100% hand-rolled inline `<svg>`. Fix the doc to match reality; do not do a mass icon-library migration (out of scope, not a styling change).
- `frontend/components/ui/button.tsx` (the shadcn/base-ui `Button`) is unused everywhere — leave it untouched. Adopting it into hand-rolled buttons is a refactor, not a styling pass.
- Every task ends in its own commit (user asked for commits per major change, not one giant commit).
- Verification per task: `cd frontend && npx tsc --noEmit && npm run lint && node node_modules/.bin/vitest --run` must stay green (per `frontend/CLAUDE.md` "Done = all three green"). Full `make lint && make test` before the final PR.

---

## File Structure

Only existing files are modified — no creates besides the plan doc itself (already written) and the final `context/ui-context.md` rewrite (existing file, content replaced).

| File | Responsibility in this plan |
|---|---|
| `frontend/app/globals.css` | New glass/status/radius tokens + background wash |
| `frontend/app/layout.tsx` | Content-column offset adjusted for inset floating sidebar |
| `frontend/components/Sidebar.tsx` | Floating glass nav panel, pill active state |
| `frontend/components/Topbar.tsx` | Blur strength bump |
| `frontend/app/page.tsx` | Empty-state landing → glass card + icon badge |
| `frontend/components/LeadSearchForm.tsx` | Boxed glass textareas, CTA, provider toggle, inline results header |
| `frontend/components/LeadCohortTable.tsx` | FiltersBar, CohortCard, status color tokens, toast |
| `frontend/components/EmailDrawer.tsx` | Floating glass drawer, reject-hover coral treatment |
| `frontend/components/RunProgressView.tsx` | Glass activity/terminal-state cards |
| `frontend/components/SyncProgressOverlay.tsx` | Glass modal panel |
| `frontend/components/RunRow.tsx` | Status badge tokens, menu radius |
| `frontend/lib/runHistory.ts` | `statusConfig()` → new success/warning/reject tokens |
| `frontend/app/history/page.tsx` | Table container glass treatment |
| `context/ui-context.md` | Final doc rewrite to match implemented state |

---

### Task 1: Design tokens — `globals.css`

**Files:**
- Modify: `frontend/app/globals.css:12-30` (theme colors), `frontend/app/globals.css:33-51` (`:root` radius/semantic), `frontend/app/globals.css:79-91` (`body` rule)

**Interfaces:**
- Produces: new Tailwind utility classes available to every later task — `bg-glass`, `bg-glass-strong`, `border-glass-edge`, `text-success`, `bg-success`, `text-success-fg`, `bg-success-soft`, `text-warning`, `bg-warning`, `text-warning-fg`, `bg-warning-soft`, `text-reject`, `bg-reject`, `bg-reject-soft`, plus the existing `rounded-sm…rounded-4xl` scale now resolving to the new larger `--radius` base.

- [ ] **Step 1: Add glass + status tokens to the `@theme` block**

In `frontend/app/globals.css`, inside the existing `@theme { ... }` block (currently lines 12-30), after the `--color-skeleton: #efede6;` line, add:

```css
  /* Glass surfaces (LeadForge design refresh) */
  --color-glass: rgba(255, 255, 255, 0.86);
  --color-glass-strong: rgba(255, 255, 255, 0.72);
  --color-glass-edge: rgba(10, 10, 10, 0.06);

  /* Status accents (LeadForge design refresh) */
  --color-success: #2cb67d;
  --color-success-fg: #1f9d66;
  --color-success-soft: rgba(44, 182, 125, 0.12);
  --color-warning: #f4a261;
  --color-warning-fg: #b9790a;
  --color-warning-soft: rgba(244, 162, 97, 0.2);
  --color-reject: #e76f51;
  --color-reject-soft: rgba(231, 111, 81, 0.06);
```

Also update the base bg/fg to the mockup's softer near-black/off-white (same family, slightly warmer):

```
  --color-bg: #fafaf7;      →   --color-bg: #f7f7f5;
  --color-fg: #0a0a0a;      →   --color-fg: #1d1d1f;
  --color-muted-fg: #a6a49b; →  --color-muted-fg: #9b9ba1;
  --color-subtle: #6a6a62;   →  --color-subtle: #6e6e73;
```

- [ ] **Step 2: Raise the shared radius base and mirror bg/fg in `:root`**

In the `:root { ... }` block, change:

```
  --background: #fafaf7;   →  --background: #f7f7f5;
  --foreground: #0a0a0a;   →  --foreground: #1d1d1f;
  --muted-foreground: #a6a49b; → --muted-foreground: #9b9ba1;
  --radius: 0.1875rem;     →  --radius: 0.875rem;
```

This changes the derived scale (already wired via `@theme inline`) from a 3px-based system to a 14px-based one: `rounded-sm`≈8px, `rounded-md`≈11px, `rounded-lg`=14px, `rounded-xl`≈20px, `rounded-2xl`≈25px, `rounded-3xl`≈31px, `rounded-4xl`≈36px. No other line needs to change — `@theme inline`'s `calc(var(--radius) * N)` block at lines 53-63 already derives from this variable.

- [ ] **Step 3: Add the background wash to `body`**

In the `@layer base { ... }` block, change the `body` rule from:

```css
  body {
    @apply bg-background text-foreground;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
  }
```

to:

```css
  body {
    @apply bg-background text-foreground;
    background-image:
      radial-gradient(circle at 6% -4%, rgba(200, 116, 46, 0.08), transparent 42%),
      radial-gradient(circle at 102% 104%, rgba(44, 182, 125, 0.06), transparent 40%);
    background-attachment: fixed;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
  }
```

This is what makes the glass/blur surfaces in later tasks actually read as "glass" — without a colored wash behind them, a translucent blurred panel over a flat single-color background looks identical to an opaque one.

- [ ] **Step 4: Verify build**

Run: `cd frontend && npm run dev` (or `npx tsc --noEmit` if you don't want to eyeball it), confirm no Tailwind/PostCSS errors, then Ctrl-C.

Expected: dev server starts clean, home page background shows a faint warm glow top-left / faint green glow bottom-right.

- [ ] **Step 5: Commit**

```bash
git add frontend/app/globals.css
git commit -m "style: add glass surface, status color, and larger-radius tokens"
```

---

### Task 2: Sidebar + layout shell

**Files:**
- Modify: `frontend/components/Sidebar.tsx:23,32,54-58,76`
- Modify: `frontend/app/layout.tsx:51`
- Modify: `frontend/components/Topbar.tsx:55`

**Interfaces:**
- Consumes: `bg-glass`, `border-glass-edge`, `rounded-xl`/`rounded-2xl` from Task 1.

- [ ] **Step 1: Float the sidebar as a glass panel**

In `frontend/components/Sidebar.tsx:23`, change:

```tsx
    <aside className="fixed left-0 top-0 bottom-0 w-[220px] bg-background border-r border-edge flex flex-col z-40">
```

to:

```tsx
    <aside className="fixed left-3 top-3 bottom-3 w-[220px] bg-glass backdrop-blur-xl border border-glass-edge rounded-2xl shadow-[0_4px_28px_rgba(0,0,0,.045)] flex flex-col z-40 overflow-hidden">
```

- [ ] **Step 2: Soften the logo image radius**

Line 32, change `className="flex-none rounded-sm"` to `className="flex-none rounded-md"`.

- [ ] **Step 3: Pill-style nav active state (drop left border)**

Lines 54-58, change:

```tsx
                  className={[
                    "flex items-center py-2 rounded-[3px] text-[13px] font-sans font-medium leading-none transition-colors border-l-2 pl-[10px] pr-3",
                    active
                      ? "text-fg bg-brand-soft border-brand"
                      : "text-subtle hover:text-fg hover:bg-skeleton border-transparent",
                  ].join(" ")}
```

to:

```tsx
                  className={[
                    "flex items-center h-[38px] px-2.5 rounded-xl text-[13.5px] font-sans font-medium leading-none transition-colors",
                    active
                      ? "text-brand bg-brand-soft"
                      : "text-subtle hover:text-fg hover:bg-skeleton",
                  ].join(" ")}
```

- [ ] **Step 4: Round the provider button group**

Line 76, change `"flex flex-col gap-1 rounded-[3px] border border-edge-input overflow-hidden text-[11px] font-sans font-medium"` to `"flex flex-col gap-1 rounded-xl border border-edge-input overflow-hidden text-[11px] font-sans font-medium"`.

- [ ] **Step 5: Adjust the content column offset in the root layout**

In `frontend/app/layout.tsx:51`, the sidebar is no longer flush against the left edge (it now sits at `left-3`, i.e. 12px in, with its own 220px width), so the content column's left margin must grow by that same 12px to preserve the visual gap. Change:

```tsx
          <div className="ml-[220px] flex flex-col min-h-screen">
```

to:

```tsx
          <div className="ml-[244px] flex flex-col min-h-screen">
```

(220px sidebar + 12px left inset + 12px gap to content = 244px.)

- [ ] **Step 6: Bump Topbar blur to match**

In `frontend/components/Topbar.tsx:55`, change `backdropFilter: "blur(10px)"` to `backdropFilter: "blur(16px)"`.

- [ ] **Step 7: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: zero errors. Then `npm run dev`, open `http://localhost:3000`, confirm the sidebar renders as a floating rounded card with a visible gap on all four sides and the content column no longer overlaps it.

- [ ] **Step 8: Commit**

```bash
git add frontend/components/Sidebar.tsx frontend/components/Topbar.tsx frontend/app/layout.tsx
git commit -m "style: float sidebar as glass panel, adjust content offset"
```

---

### Task 3: Empty-state landing (`/`)

**Files:**
- Modify: `frontend/app/page.tsx` (full rewrite of the `Home` component body)

**Interfaces:**
- Consumes: `bg-glass`, `border-glass-edge`, `rounded-3xl`, `--color-brand-soft` from Task 1.

- [ ] **Step 1: Wrap the empty state in a glass card with an icon badge**

Replace the full contents of `frontend/app/page.tsx` with:

```tsx
import Link from "next/link";

export default function Home() {
  return (
    <section className="flex flex-col flex-1 items-center justify-center min-h-[calc(100vh-60px)] px-8">
      <div className="text-center max-w-[420px] rounded-3xl border border-glass-edge bg-glass backdrop-blur-xl shadow-[0_10px_36px_rgba(0,0,0,.05)] px-10 py-11">
        <div className="mx-auto mb-6 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-soft">
          <svg
            width="23"
            height="23"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-brand"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
        </div>
        <p className="font-mono font-medium text-[11px] uppercase tracking-[.18em] text-muted-fg mb-4">
          No runs yet
        </p>
        <h1 className="font-serif text-[26px] leading-[1.35] tracking-[-0.015em] text-fg mb-8">
          Start a search to find your first cohort of leads.
        </h1>
        <Link
          href="/search"
          className="inline-flex items-center gap-2 bg-brand text-white text-[14px] font-sans font-semibold rounded-2xl px-6 py-3 shadow-[0_8px_22px_rgba(200,116,46,.32)] hover:scale-[1.02] transition-transform"
        >
          New search
        </Link>
      </div>
    </section>
  );
}
```

- [ ] **Step 2: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: zero errors.

- [ ] **Step 3: Commit**

```bash
git add frontend/app/page.tsx
git commit -m "style: glass card treatment for empty-state landing"
```

---

### Task 4: LeadSearchForm — new-search form + inline results header

**Files:**
- Modify: `frontend/components/LeadSearchForm.tsx:88,94,100,135-142,159-166,204,211-217,231-237`

**Interfaces:**
- Consumes: tokens from Task 1. No prop/behavior changes — `handleSubmit`, `startSearch`, state hooks all untouched.

- [ ] **Step 1: Inline sync-results header — round the "← New search" button**

Line 88, change `"inline-flex items-center gap-2 rounded-[3px] border border-edge px-4 py-2 font-sans text-[13px] font-medium text-fg hover:bg-surface transition-colors"` to `"inline-flex items-center gap-2 rounded-xl border border-glass-edge bg-glass backdrop-blur-md px-4 py-2 font-sans text-[13px] font-medium text-fg hover:bg-surface transition-colors"`.

- [ ] **Step 2: Empty-results box**

Line 94, change `"rounded-[3px] border border-edge bg-surface px-6 py-10 text-center"` to `"rounded-2xl border border-glass-edge bg-glass backdrop-blur-md px-6 py-10 text-center"`.

- [ ] **Step 3: Prompt textarea — boxed glass treatment (replaces underline style)**

Lines 135-142, change:

```tsx
          className={cn(
            "w-full resize-none bg-transparent outline-none",
            "border-b border-[#161613] pb-2 pt-2",
            "font-serif text-[24px] leading-[1.35] text-fg placeholder:text-[#B0AEA4]",
            "focus:border-brand transition-colors",
            "disabled:opacity-50",
          )}
```

to:

```tsx
          className={cn(
            "w-full resize-none outline-none",
            "rounded-2xl border border-edge-input bg-glass backdrop-blur-md px-5 py-4 shadow-[0_6px_22px_rgba(0,0,0,.04)]",
            "font-serif text-[22px] leading-[1.35] text-fg placeholder:text-muted-fg",
            "focus:border-brand/40 transition-colors",
            "disabled:opacity-50",
          )}
```

- [ ] **Step 4: Sender-context textarea — same boxed treatment, smaller**

Lines 159-166, change:

```tsx
            className={cn(
              "w-full resize-none bg-transparent outline-none",
              "border-b border-edge-input pb-2 pt-1",
              "font-sans text-[14px] leading-[1.6] text-fg placeholder:text-muted-fg",
              "focus:border-brand transition-colors",
              "disabled:opacity-50",
            )}
```

to:

```tsx
            className={cn(
              "w-full resize-none outline-none",
              "rounded-2xl border border-edge-input bg-glass backdrop-blur-md px-4 py-3",
              "font-sans text-[14px] leading-[1.6] text-fg placeholder:text-muted-fg",
              "focus:border-brand/40 transition-colors",
              "disabled:opacity-50",
            )}
```

- [ ] **Step 5: Provider toggle container radius**

Line 204, change `"inline-flex flex-wrap border border-edge-input rounded-[4px] overflow-hidden text-[11px] font-sans font-medium"` to `"inline-flex flex-wrap border border-edge-input rounded-xl overflow-hidden text-[11px] font-sans font-medium"`.

- [ ] **Step 6: Submit button — filled brand pill with lift**

Lines 231-237, change:

```tsx
            className={cn(
              "inline-flex items-center gap-2 bg-brand text-white",
              "font-sans font-semibold text-[14px] leading-none",
              "rounded-[3px] px-6 py-[11px]",
              "hover:brightness-90 transition-[filter]",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
```

to:

```tsx
            className={cn(
              "inline-flex items-center gap-2 bg-brand text-white",
              "font-sans font-semibold text-[14px] leading-none",
              "rounded-2xl px-8 py-[13px] shadow-[0_8px_24px_rgba(200,116,46,.35)]",
              "hover:scale-[1.02] transition-transform",
              "disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100",
            )}
```

- [ ] **Step 7: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run lint && node node_modules/.bin/vitest --run LeadSearchForm`
Expected: zero errors, `LeadSearchForm.test.tsx` still passes (it queries by role/label text, unaffected by className changes).

- [ ] **Step 8: Commit**

```bash
git add frontend/components/LeadSearchForm.tsx
git commit -m "style: glass card treatment for new-search form"
```

---

### Task 5: LeadCohortTable — filters, cohort cards, status tokens

**Files:**
- Modify: `frontend/components/LeadCohortTable.tsx:13-23,35,77-81,107,120,127,286,314,331`

**Interfaces:**
- Consumes: `--color-success`/`success-fg`/`success-soft`, `--color-warning`/`warning-fg`/`warning-soft`, `--color-reject` from Task 1.
- Produces: no interface change — `BUCKET_COLORS` and `ScoreBadge` keep the same shape/usage, only their class strings change.

- [ ] **Step 1: Replace hardcoded Tailwind palette in `BUCKET_COLORS` and `ScoreBadge` with new tokens**

Lines 13-23, change:

```tsx
const BUCKET_COLORS: Record<string, string> = {
  high: "text-emerald-700 bg-emerald-50 border-emerald-200",
  mid: "text-amber-700 bg-amber-50 border-amber-200",
  low: "text-slate-600 bg-slate-50 border-slate-200",
};

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const col = pct > 80 ? "text-emerald-700" : pct >= 50 ? "text-amber-700" : "text-slate-500";
  return <span className={cn("font-mono text-[11px] tabular-nums", col)}>{pct}%</span>;
}
```

to:

```tsx
const BUCKET_COLORS: Record<string, string> = {
  high: "text-success-fg bg-success-soft border-success/30",
  mid: "text-warning-fg bg-warning-soft border-warning/40",
  low: "text-subtle bg-skeleton border-edge",
};

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const col = pct > 80 ? "text-success-fg" : pct >= 50 ? "text-warning-fg" : "text-subtle";
  return <span className={cn("font-mono text-[11px] tabular-nums", col)}>{pct}%</span>;
}
```

- [ ] **Step 2: FiltersBar container → glass card**

Line 35, change `"mb-5 flex flex-wrap items-center gap-4 rounded-[3px] border border-edge bg-surface px-4 py-2.5"` to `"mb-5 flex flex-wrap items-center gap-4 rounded-2xl border border-glass-edge bg-glass backdrop-blur-md shadow-[0_6px_24px_rgba(0,0,0,.04)] px-4 py-2.5"`.

- [ ] **Step 3: Industry filter chips → pill shape**

Lines 77-81, change:

```tsx
                className={cn(
                  "rounded-[3px] border px-2 py-0.5 font-sans text-[11px] transition-colors",
                  active
                    ? "border-brand bg-brand-soft text-brand"
                    : "border-edge bg-white text-muted-fg hover:text-fg",
                )}
```

to:

```tsx
                className={cn(
                  "rounded-full border px-2.5 py-0.5 font-sans text-[11px] transition-colors",
                  active
                    ? "border-brand bg-brand-soft text-brand"
                    : "border-edge bg-white text-muted-fg hover:text-fg",
                )}
```

- [ ] **Step 4: CohortCard container → glass card**

Line 107, change `"rounded-[3px] border border-edge"` to `"rounded-2xl border border-glass-edge bg-glass backdrop-blur-md shadow-[0_6px_24px_rgba(0,0,0,.04)] overflow-hidden"`.

- [ ] **Step 5: CohortCard "Approve all" button radius**

Line 127, change `"shrink-0 rounded-[3px] bg-brand px-3 py-1.5 font-sans text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-40"` to `"shrink-0 rounded-xl bg-brand px-3 py-1.5 font-sans text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-40"`.

- [ ] **Step 6: Row decision text color**

Line 163-164 area — inside the `<td>` decision span, change:

```tsx
                    lead.decision === "approved" ? "text-emerald-700" : lead.decision === "rejected" ? "text-red-600" : "text-muted-fg",
```

to:

```tsx
                    lead.decision === "approved" ? "text-success-fg" : lead.decision === "rejected" ? "text-reject" : "text-muted-fg",
```

- [ ] **Step 7: Header approve/export button radius**

Line 286, change `"inline-flex items-center gap-1.5 rounded-[3px] px-3 py-1.5",` to `"inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5",`.

- [ ] **Step 8: Empty-filters box**

Line 314, change `"rounded-[3px] border border-edge px-6 py-8 text-center font-sans text-[13px] text-muted-fg"` to `"rounded-2xl border border-glass-edge bg-glass backdrop-blur-md px-6 py-8 text-center font-sans text-[13px] text-muted-fg"`.

- [ ] **Step 9: Toast**

Line 331, change `"fixed bottom-6 left-1/2 -translate-x-1/2 rounded-[3px] border border-edge bg-surface px-4 py-2 font-sans text-[12px] text-fg shadow-lg"` to `"fixed bottom-6 left-1/2 -translate-x-1/2 rounded-xl border border-glass-edge bg-glass backdrop-blur-md px-4 py-2 font-sans text-[12px] text-fg shadow-lg"`.

- [ ] **Step 10: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run lint && node node_modules/.bin/vitest --run LeadCohortTable`
Expected: zero errors, `LeadCohortTable.test.tsx` still passes.

- [ ] **Step 11: Commit**

```bash
git add frontend/components/LeadCohortTable.tsx
git commit -m "style: glass cards and status-color tokens for cohort review table"
```

---

### Task 6: EmailDrawer — floating glass panel

**Files:**
- Modify: `frontend/components/EmailDrawer.tsx:59-64,103,114,130,145,152,158`

**Interfaces:**
- Consumes: `--color-reject`, `--color-reject-soft`, `bg-glass`, `rounded-2xl`/`3xl` from Task 1. No prop/behavior change.

- [ ] **Step 1: Backdrop + panel — inset floating glass card (was edge-to-edge solid)**

Lines 59-64, change:

```tsx
      <div
        className="fixed inset-0 z-20 bg-black/20"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className="fixed right-0 top-0 z-30 flex h-full w-[480px] flex-col border-l border-edge bg-surface shadow-xl">
```

to:

```tsx
      <div
        className="fixed inset-0 z-20 bg-black/25 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className="fixed right-3 top-3 bottom-3 z-30 flex w-[420px] flex-col rounded-3xl border border-glass-edge bg-glass backdrop-blur-2xl shadow-[0_8px_32px_rgba(0,0,0,.06)] overflow-hidden">
```

- [ ] **Step 2: Subject input radius**

Line 103, change `"rounded-[3px] border border-edge bg-white px-3 py-2 font-sans text-[13px] text-fg outline-none focus:border-brand"` to `"rounded-xl border border-edge-input bg-white/70 px-3 py-2 font-sans text-[13px] text-fg outline-none focus:border-brand/50"`.

- [ ] **Step 3: Body textarea radius**

Line 114, change `"h-full min-h-[240px] flex-1 resize-none rounded-[3px] border border-edge bg-white px-3 py-2 font-sans text-[13px] text-fg outline-none focus:border-brand"` to `"h-full min-h-[240px] flex-1 resize-none rounded-2xl border border-edge-input bg-white/70 px-3 py-2 font-sans text-[13px] text-fg outline-none focus:border-brand/50"`.

- [ ] **Step 4: Hooks chips → pill shape**

Line 130, change `"rounded-[3px] border border-edge bg-white px-2 py-0.5 font-mono text-[10px] text-muted-fg"` to `"rounded-full border border-edge bg-white/70 px-2.5 py-0.5 font-mono text-[10px] text-muted-fg"`.

- [ ] **Step 5: "Save draft" button radius**

Line 145, change `"rounded-[3px] border border-edge px-3 py-1.5 font-sans text-[12px] text-muted-fg hover:text-fg disabled:opacity-40"` to `"rounded-xl border border-edge px-3 py-1.5 font-sans text-[12px] text-muted-fg hover:text-fg disabled:opacity-40"`.

- [ ] **Step 6: "Reject" button — coral hover treatment matching mockup**

Line 152, change `"rounded-[3px] border border-edge px-4 py-1.5 font-sans text-[12px] text-fg hover:border-fg"` to `"rounded-xl border border-edge px-4 py-1.5 font-sans text-[12px] text-fg hover:border-reject/40 hover:text-reject hover:bg-reject-soft transition-colors"`.

- [ ] **Step 7: "Approve" button — filled brand with lift**

Line 158, change `"rounded-[3px] bg-brand px-4 py-1.5 font-sans text-[12px] font-medium text-white hover:opacity-90"` to `"rounded-xl bg-brand px-4 py-1.5 font-sans text-[12px] font-medium text-white shadow-[0_8px_20px_rgba(200,116,46,.32)] hover:scale-[1.02] transition-transform"`.

- [ ] **Step 8: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run lint`
Expected: zero errors. (No dedicated `EmailDrawer.test.tsx` exists — smoke-test manually per Task 8.)

- [ ] **Step 9: Commit**

```bash
git add frontend/components/EmailDrawer.tsx
git commit -m "style: float EmailDrawer as glass panel, add reject-hover treatment"
```

---

### Task 7: Run-progress views + history table — glass containers and status tokens

**Files:**
- Modify: `frontend/components/RunProgressView.tsx:125,139,161,170`
- Modify: `frontend/components/SyncProgressOverlay.tsx:55,73`
- Modify: `frontend/components/RunRow.tsx:88-90,117,134`
- Modify: `frontend/lib/runHistory.ts` (the `statusConfig` function)
- Modify: `frontend/app/history/page.tsx:18,60,67,77`

**Interfaces:**
- Consumes: `--color-success-soft`/`success-fg`, `--color-warning-soft`/`warning-fg`, `--color-reject-soft`/`reject` from Task 1.
- `statusConfig()` keeps its `StatusConfig { label: string; className: string }` return shape — only the class strings inside change, so `RunRow.tsx`'s `cfg.className` usage at line 89 needs no change itself.

- [ ] **Step 1: `statusConfig` → token-driven classes**

In `frontend/lib/runHistory.ts`, change the `statusConfig` function body from:

```ts
export function statusConfig(status: string): StatusConfig {
  switch (status) {
    case "completed":
      return { label: "Completed", className: "bg-emerald-50 text-emerald-700 border-emerald-200" };
    case "failed":
      return { label: "Failed", className: "bg-red-50 text-red-700 border-red-200" };
    case "scraping":
      return { label: "Scraping", className: "bg-amber-50 text-amber-700 border-amber-200" };
    case "qualifying":
      return { label: "Qualifying", className: "bg-amber-50 text-amber-700 border-amber-200" };
    case "generating":
      return { label: "Generating", className: "bg-amber-50 text-amber-700 border-amber-200" };
    default:
      return { label: status, className: "bg-slate-50 text-slate-600 border-slate-200" };
  }
}
```

to:

```ts
export function statusConfig(status: string): StatusConfig {
  switch (status) {
    case "completed":
      return { label: "Completed", className: "bg-success-soft text-success-fg border-success/30" };
    case "failed":
      return { label: "Failed", className: "bg-reject-soft text-reject border-reject/30" };
    case "scraping":
      return { label: "Scraping", className: "bg-warning-soft text-warning-fg border-warning/40" };
    case "qualifying":
      return { label: "Qualifying", className: "bg-warning-soft text-warning-fg border-warning/40" };
    case "generating":
      return { label: "Generating", className: "bg-warning-soft text-warning-fg border-warning/40" };
    default:
      return { label: status, className: "bg-skeleton text-subtle border-edge" };
  }
}
```

- [ ] **Step 2: `RunRow.tsx` — status badge and menu radius**

Line 88, change `"inline-flex items-center rounded-[3px] border px-2 py-0.5 font-mono text-[10px]",` to `"inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-[10px]",` (badge shape only — `cfg.className` colors already fixed by Step 1).

Line 117, change `"absolute right-4 top-full z-20 mt-1 min-w-[140px] rounded-[3px] border border-edge bg-surface shadow-lg py-1"` to `"absolute right-4 top-full z-20 mt-1 min-w-[140px] rounded-xl border border-edge bg-surface shadow-lg py-1"`.

Line 134, change `"rounded-[3px] border border-edge bg-surface p-0 shadow-xl backdrop:bg-black/30 w-[360px] open:flex open:flex-col"` to `"rounded-2xl border border-edge bg-surface p-0 shadow-xl backdrop:bg-black/30 w-[360px] open:flex open:flex-col"`.

- [ ] **Step 3: `RunProgressView.tsx` — glass containers**

Line 125, change `"mb-6 rounded-[3px] border border-edge bg-surface px-4 py-2.5 font-mono text-[11px] text-muted-fg"` to `"mb-6 rounded-2xl border border-glass-edge bg-glass backdrop-blur-md px-4 py-2.5 font-mono text-[11px] text-muted-fg"`.

Line 139, change `"mb-8 rounded-[3px] border border-edge bg-surface p-4"` to `"mb-8 rounded-2xl border border-glass-edge bg-glass backdrop-blur-md p-4"`.

Line 161, change `"rounded-[3px] border border-brand/30 bg-brand-soft px-5 py-4"` to `"rounded-2xl border border-brand/25 bg-brand-soft px-5 py-4"`.

Line 170, change `"rounded-[3px] border border-edge bg-surface px-5 py-4"` to `"rounded-2xl border border-glass-edge bg-glass backdrop-blur-md px-5 py-4"`.

- [ ] **Step 4: `SyncProgressOverlay.tsx` — glass modal panel**

Line 55, change `"w-full max-w-xl rounded-[3px] border border-edge bg-surface px-8 py-10 shadow-[0_8px_40px_rgba(10,10,10,0.08)]"` to `"w-full max-w-xl rounded-3xl border border-glass-edge bg-glass backdrop-blur-2xl px-8 py-10 shadow-[0_10px_36px_rgba(0,0,0,.06)]"`.

Line 73, change `"mt-8 rounded-[3px] border border-edge bg-background p-4"` to `"mt-8 rounded-2xl border border-glass-edge bg-glass-strong backdrop-blur-md p-4"`.

- [ ] **Step 5: `history/page.tsx` — table + CTA + disabled-state box**

Line 18 (demo-mode disabled box) and line 67 (empty-runs box), both change `"rounded-[3px] border border-edge bg-surface px-6 py-10 text-center"` to `"rounded-2xl border border-glass-edge bg-glass backdrop-blur-md px-6 py-10 text-center"`.

Line 60, change `"inline-flex items-center gap-2 rounded-[3px] bg-brand px-4 py-2 font-sans text-[13px] font-medium text-white hover:brightness-90 transition-[filter]"` to `"inline-flex items-center gap-2 rounded-xl bg-brand px-4 py-2 font-sans text-[13px] font-medium text-white hover:brightness-90 transition-[filter]"`.

Line 77, change `"rounded-[3px] border border-edge overflow-hidden"` to `"rounded-2xl border border-glass-edge bg-glass backdrop-blur-md overflow-hidden"`.

- [ ] **Step 6: Verify**

Run: `cd frontend && npx tsc --noEmit && npm run lint && node node_modules/.bin/vitest --run`
Expected: zero errors, full suite green (all three `.test.tsx` files pass unchanged).

- [ ] **Step 7: Commit**

```bash
git add frontend/components/RunProgressView.tsx frontend/components/SyncProgressOverlay.tsx frontend/components/RunRow.tsx frontend/lib/runHistory.ts frontend/app/history/page.tsx
git commit -m "style: glass containers and status-color tokens for progress views and history"
```

---

### Task 8: Manual smoke test

**Files:** none (verification only)

- [ ] **Step 1: Start the app in demo mode**

Run: `cd frontend && EXECUTION_MODE=sync PERSISTENCE_ENABLED=false npm run dev` (matches how `make frontend` runs it in this repo's demo mode — confirm the exact env flags against `.env.example` if these two alone don't produce the sync/demo code paths).

- [ ] **Step 2: Click through every touched screen**

- `/` — empty-state glass card renders, icon badge visible, CTA button has hover-scale.
- `/search` — prompt/sender-context boxes are glass cards with visible border+blur, submit button is a filled rounded pill.
- Submit a search (demo mode runs sync) — confirm `SyncProgressOverlay` glass modal appears, then the inline `LeadCohortTable` results render with rounded cohort cards, pill filter chips, and status colors (green/amber/gray) matching qualified/borderline/disqualified.
- Click a lead row → `EmailDrawer` opens as an inset floating glass panel on the right; hover the Reject button and confirm the coral hover treatment.
- Visit `/history` (if `PERSISTENCE_ENABLED` allows it) — confirm the glass table container and pill status badges.
- Resize the window narrow — since layout offsets changed (`ml-[244px]`), confirm nothing overlaps or clips at common widths (1280px, 1440px).

- [ ] **Step 3: Report back**

No commit for this task — it's verification only. If any visual issue is found, fix it as a follow-up within the relevant task's file before moving to Task 9.

---

### Task 9: Update `context/ui-context.md`

**Files:**
- Modify: `context/ui-context.md` (full rewrite)

**Interfaces:**
- None — documentation only, must match the tokens actually added in Task 1 and the patterns actually implemented in Tasks 2-7.

- [ ] **Step 1: Rewrite the doc to reflect the new token set, radius scale, glass pattern, and correct the icon-library inaccuracy**

Replace the full contents of `context/ui-context.md` with:

```markdown
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
```

- [ ] **Step 2: Sanity-check the doc against the actual code**

Run: `grep -rn "rounded-\[3px\]\|rounded-\[4px\]" frontend/components frontend/app` — expect **zero** matches (everything from Tasks 2-7 should have been converted). If any remain, they were missed in an earlier task — go back and fix them there (keep the fix in that task's commit boundary conceptually, but a trailing `git commit --fixup` style follow-up in this task's commit is acceptable too — just don't leave hardcoded pixel radii in the diff).

- [ ] **Step 3: Commit**

```bash
git add context/ui-context.md
git commit -m "docs: update ui-context.md for the LeadForge glass restyle"
```

---

### Task 10: Final verification and PR

**Files:** none

- [ ] **Step 1: Full check suite**

Run from repo root: `make lint && make test`
Expected: all green (ruff, mypy, pytest untouched/unaffected; eslint, tsc, vitest, prisma generate all clean for the frontend changes).

- [ ] **Step 2: Push and open PR**

```bash
git push -u origin feat/leadforge-glass-restyle
gh pr create --base main
```

Fill the PR template per `.github/pull_request_template.md`: one-sentence summary ("Restyle existing frontend screens to match the imported LeadForge Claude Design mockup — glass surfaces, larger radii, status color tokens"), note in the invariants checklist that this is a pure frontend styling change (no schema/API/Temporal/DSPy touched), and describe the manual smoke test from Task 8 in the verification checklist.

- [ ] **Step 3: Report the PR URL back to the user and stop — do not merge.**

---

## Self-Review Notes

- **Spec coverage**: every existing screen/component identified in the frontend survey (Sidebar, Topbar, `/`, `/search` + inline results, `LeadCohortTable`, `EmailDrawer`, `RunProgressView`, `SyncProgressOverlay`, `RunRow`, `/history`) has a task. Explicitly-skipped mockup sections (Feed, saved searches, credits meter, ICP chips, geo slider, 2 of 3 empty-state variants) are listed in Global Constraints so no task accidentally builds them.
- **Placeholder scan**: no "TBD"/"handle appropriately" language — every step names the exact file, line range, and old→new string.
- **Type consistency**: `statusConfig()`'s `StatusConfig { label, className }` shape is unchanged (Task 7 Step 1) so `RunRow.tsx`'s existing `cfg.className` / `cfg.label` usage needs no signature changes — verified by reading `RunRow.tsx` line 89/92 before writing Task 7.
