@AGENTS.md

# Frontend — Claude Code Instructions

## Commands (run from `frontend/`)

```bash
node node_modules/.bin/prisma generate   # regenerate types — always before tsc
npx tsc --noEmit                          # type check
npm run lint                              # eslint
node node_modules/.bin/vitest --run      # unit tests
```

From the project root:
```bash
make db-push     # prisma db push --accept-data-loss + generate (needs postgres)
make test        # pytest + vitest
make lint        # ruff + eslint
make frontend    # next dev
```

> Node version: use `~/.n/bin/node` (v20). System node is v18 and breaks vitest + prisma CLI.
> `make` targets export the correct PATH automatically.

---

## Workflow: before writing code

1. Read `AGENTS.md` (included above) for Next.js 16 / React 19 / Tailwind v4 / Prisma 7 gotchas
2. Check `node_modules/next/dist/docs/` for the authoritative API reference — training data
   is stale for Next.js 16
3. If schema changed: `node node_modules/.bin/prisma generate`
4. Confirm the component needs `"use client"` before adding it — default to Server Component

---

## Done = all three green

```bash
node node_modules/.bin/prisma generate   # fresh types
npx tsc --noEmit                          # zero errors
node node_modules/.bin/vitest --run      # all pass
npm run lint                              # zero eslint errors
```

---

## File layout

```
frontend/
  app/
    generated/prisma/   ← gitignored; rebuilt by prisma generate
    layout.tsx          ← root layout, Server Component
    page.tsx            ← home page, Server Component
  lib/
    prisma.ts           ← PrismaClient singleton (PrismaPg adapter); import from here only
    api.ts              ← typed fetch wrappers for backend; server-side only
    utils.ts            ← cn() and pure helpers
  components/           ← shared UI; prefer Server Components; "use client" only at leaves
  prisma/
    schema.prisma       ← Prisma 7 schema (app schema, custom output)
  prisma.config.ts      ← datasource URL, loads root .env via fileURLToPath
```

---

## Anti-patterns

| ❌ Don't | ✅ Do instead |
|---|---|
| `import { PrismaClient } from "@prisma/client"` | `from "@/app/generated/prisma/client"` |
| `new PrismaClient()` in a component | `import { prisma } from "@/lib/prisma"` |
| `params.id` without `await params` | `const { id } = await params` |
| `useFormState` from react-dom | `useActionState` from react |
| Webpack plugin in `next.config.ts` | Turbopack only — no webpack config |
| `tailwind.config.js` | `@theme {}` in `globals.css` |
| `lib/api.ts` called from a Client Component | Wrap in a Server Action first |
| Fetching data in `useEffect` | Server Component + `"use cache"` |
| `"use client"` on a layout or page | Push it down to the interactive leaf only |
