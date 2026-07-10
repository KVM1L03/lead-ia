# LeadIA — Roadmap

Planned work in rough priority order. Items are independent unless noted.

**Resolved:** SerpAPI free-tier cost (250 searches/month ≈ 10 runs/month) was a risk for sustained personal use. Resolved by adding `GooglePlacesProvider` (`MAPS_PROVIDER=google_places`) with 5,000 free Text Search calls/month. The tradeoff: `rating`/`review_count` are `None` on the google_places path (FieldMask must exclude them to stay at the Pro tier — see "Three maps providers, and SKU-tier cost engineering" in the README and `docs/cost-guardrails.md`).

---

## 1. Terraform / infrastructure (near-term)

- Finish and validate the GCP Terraform modules in `infra/terraform/`: VPC, Artifact Registry, serverless VPC connector, Cloud Run services (api-gateway + ai-worker), Cloud SQL.
- Document the deploy runbook end-to-end (build → push image → `terraform apply` → smoke test).
- Add a CI job that runs `terraform validate` + `terraform plan` on PRs touching `infra/`.
- Decide whether to keep Langfuse self-hosted on a small GCE VM or move to Langfuse Cloud (cost vs. data-residency tradeoff).

---

## 2. Gemini migration (near-term, blocked on eval gate)

Full checklist in [`docs/model-choices.md` § Migration plan](model-choices.md#migration-plan-gemini-primary). Short version:

1. Run DSPy-path qualifier eval (not just plain-prompt promptfoo) — this is the merge gate.
2. If Gemini ≥ Haiku on DSPy path: flip `_DEFAULTS["qualifier"]` in `llm_router.py`, add Temporal smoke + Langfuse review.
3. Human email eval (Sonnet vs Gemini, ~20 leads, blind review) → flip `_DEFAULTS["email"]`.
4. Both flips are separate PRs. Rollback via `QUALIFIER_MODEL` / `EMAIL_MODEL` env vars.

**Do not merge router changes without the eval checklist complete.**

---

## 3. Frontend — responsive layout (near-term)

The approval UI works on desktop but is not mobile-friendly. Priority fixes:

- Lead card grid: switch from fixed-width columns to responsive breakpoints (Tailwind `sm:` / `md:`).
- Approval toolbar: make approve/reject buttons accessible on small screens (sticky bottom bar on mobile).
- Email draft panel: collapsible on mobile; full-width on desktop.
- Test at 375 px (iPhone SE) and 768 px (iPad) breakpoints.

---

## 4. Demo UX + missing tools (medium-term)

- **Better empty states:** first-time user flow — what to type, example prompts, expected wait time.
- **Progress feedback:** the sync path currently has no server-sent events. Add a simple SSE or polling endpoint so the UI shows per-lead progress (not just a spinner).
- **Prompt history:** persist the last N prompts per session (localStorage is fine for demo; no auth needed).
- **Audit which tools are missing:** after 10+ real demo sessions, identify the top 2-3 friction points before building anything.

---

## 5. Full application: auth, accounts, persistence (long-term)

This is a significant scope expansion — do not start until items 1–4 are stable.

- **Auth:** Supabase Auth (email + OAuth). All API routes gated; anonymous demo mode optional.
- **Sessions:** per-user run history stored in Supabase (replace the current ephemeral Postgres approach). Frontend reads from Supabase directly via Row Level Security.
- **Accounts:** user profile, API key storage (BYOK per-user, encrypted at rest), usage dashboard.
- **Billing guardrails:** per-user monthly lead cap, Stripe integration for paid tiers.
- **Email sending:** ESP integration (Resend or Postmark), domain warming, deliverability monitoring, unsubscribe handling.
- **Multi-region:** Cloud Run is currently single-region. Global B2B prospecting has latency and data-residency implications.

**Dependency:** items 3 and 4 (responsive UI + UX audit) should be done first — no point auth-gating a UI that isn't polished.
