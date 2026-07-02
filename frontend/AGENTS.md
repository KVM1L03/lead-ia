# Frontend Agent Rules — LeadForge

Stack: Next.js 16 · React 19 · Tailwind v4 · Prisma 7 · @base-ui/react · TypeScript strict

Read this file before touching any file under `frontend/`. Every item below is a real
breaking change or gotcha in the current major versions — not general advice.

---

## Next.js 16 — What Changed

### Async request APIs (breaking)
`params`, `searchParams`, `cookies()`, `headers()` are **all async Promises** now.

```ts
// ✅ Next.js 16
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params
}

// ❌ was valid in 14/15 — runtime error in 16
export default function Page({ params }: { params: { id: string } }) {
  const id = params.id
}
```

### Caching is opt-in — `"use cache"` directive
The implicit fetch cache from Next.js 13–15 is gone. Nothing is cached unless you
explicitly opt in with the `"use cache"` directive at the top of a file, component,
or async function.

```ts
// Cache a Server Component
"use cache"
export default async function RunList() { ... }

// Cache a data helper with a tag for targeted revalidation
"use cache"
export async function getRuns() {
  cacheTag("runs")
  return prisma.run.findMany()
}
```

Invalidate from a Server Action: `revalidateTag("runs")`.
Never call `cookies()` / `headers()` / `searchParams` **inside** a cached scope —
read them outside first, then pass as arguments.

### Bundler: Turbopack only
Turbopack is the default and only supported bundler. Webpack config in `next.config.ts`
is silently ignored. Do not add webpack plugins.

### Removed in 16
- Legacy AMP
- `runtime` page export (use route segment config: `export const runtime = "edge"`)
- `next/font` `subsets` option → use `display` + `variable`
- `unstable_rootParams`

---

## React 19 — Patterns

### `useActionState` (replaces removed `useFormState`)
```ts
// ✅ React 19
import { useActionState } from "react"
const [state, action, isPending] = useActionState(serverAction, initialState)

// ❌ removed
import { useFormState } from "react-dom"
```

### `useOptimistic`
React auto-reverts if the Server Action throws. No manual rollback logic needed.
```ts
const [optimisticLeads, addOptimistic] = useOptimistic(leads)
```

### `use()` hook
Unwrap a Promise or Context inside a render without `await` or `useEffect`:
```ts
const data = use(fetchLeadsPromise)  // suspends until resolved
```

### Default: Server Component
Everything in `app/` is a Server Component unless you add `"use client"`. Never
add `"use client"` just to use state — lift only the interactive leaf to a small
client component and keep the parent server-side.

---

## Tailwind v4 — CSS-First Config

No `tailwind.config.js`. All configuration lives in `globals.css`.

```css
/* ✅ v4 */
@import "tailwindcss";
@theme {
  --color-brand: oklch(55% 0.18 260);
  --font-sans: "Inter", sans-serif;
}
@utility focus-ring {
  @apply outline-2 outline-offset-2 outline-brand;
}

/* ❌ v3 syntax — broken in v4 */
@tailwind base;
@tailwind components;
@tailwind utilities;
```

- PostCSS plugin: `@tailwindcss/postcss` (not `tailwindcss`)
- `@theme` variables are available as both Tailwind utilities AND `var(--color-brand)`
- `ring` default changed: 1px / currentColor (was 3px / blue-500) — always specify
  width and color explicitly: `ring-2 ring-blue-500`
- Arbitrary CSS variables use parens: `bg-(--my-var)` (not brackets)

---

## Prisma 7 — Rules

### Generator name changed
```prisma
generator client {
  provider = "prisma-client"        // NOT "prisma-client-js"
  output   = "../app/generated/prisma"
}
```

### Import path: custom output, not @prisma/client
```ts
// ✅ this project
import { PrismaClient } from "@/app/generated/prisma/client"

// ❌ wrong for a custom output location
import { PrismaClient } from "@prisma/client"
```

### Driver adapter is mandatory (no built-in query engine)
```ts
import { PrismaPg } from "@prisma/adapter-pg"
import pg from "pg"
const pool = new pg.Pool({ connectionString: process.env.PRISMA_DATABASE_URL })
const adapter = new PrismaPg(pool)
export const prisma = new PrismaClient({ adapter })
```

Singleton lives in `lib/prisma.ts` — instantiate `PrismaClient` exactly once.

### `previewFeatures = ["driverAdapters"]`
Currently in the schema but deprecated (adapter is now stable). It produces a
warning, not an error. Leave it in place until the schema is intentionally edited.

### Env var: PRISMA_DATABASE_URL
Use `postgresql://...` format. `APP_DATABASE_URL` uses `postgresql+asyncpg://...`
which is SQLAlchemy-specific and will break Prisma's connection.

### `prisma generate` must run before `tsc`
Generated types are gitignored (`/app/generated/prisma`). CI runs
`npx prisma generate` before `npx tsc --noEmit`. Locally: same order.
The `make db-push` target handles both.

---

## TypeScript

- `strict: true`, `noEmit: true` in tsconfig — all code must pass `npx tsc --noEmit` clean
- Path alias `@/*` maps to the `frontend/` root
- No `as unknown as X`, no `any` — use `satisfies`, proper generics, or type narrowing
- Server Action return types must be explicit — inferred `void` breaks `useActionState`

---

## Architecture Constraints

- **No Prisma in Client Components** — only Server Components and Server Actions call `prisma`
- **No direct backend calls from the browser** — `lib/api.ts` wrappers are server-side only;
  wrap them in a Server Action if you need to trigger them from a Client Component
- **No `useState` + `useEffect` for server data** — use Server Components +
  `"use cache"` + `revalidateTag`
- **One `"use client"` boundary per feature** — keep interactive islands small;
  don't bubble the directive up to a layout
- **Shadcn via `@base-ui/react`** — do not `npm install @shadcn/ui` or `radix-ui` directly
- **No new ORM** — Prisma is the only data layer; SQLAlchemy lives on the backend
