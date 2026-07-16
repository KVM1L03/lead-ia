# LeadIA (LeadForge) — Project Overview

## Overview

LeadIA is a portfolio-grade, AI-powered B2B lead generation pipeline:
prompt → Google Places (via SerpAPI) → cheap-model qualifier → email draft →
human approval. It collapses the search-qualify-write loop of manual B2B
prospecting into a single pipeline that a human reviews and approves before
anything leaves the tool. Local-first, BYOK — not a hosted multi-tenant
product.

## Goals

1. Automate the search → qualify → write loop for B2B prospecting while
   keeping a human approval gate before anything leaves the tool.
2. Showcase production-grade AI engineering patterns: durable workflows
   (Temporal), typed LLM extraction (DSPy), LLM observability (Langfuse),
   zero-trust tool access (MCP), and evaluations (Promptfoo + DSPy).
3. Stay cheap and BYOK — no hosted multi-tenant infrastructure, no billing,
   no email sending.

## Core User Flow

1. User describes an ICP prompt (e.g. "dental practices in Warsaw with no
   online booking"), optionally adds a line about themselves, and picks how
   many leads to find.
2. The pipeline parses the prompt into a Maps search query (DSPy) and
   searches Google Maps via the MCP bridge → SerpAPI or Google Places.
3. Each business is enriched, then qualified against the ICP with a cheap,
   fast model (Haiku 4.5).
4. Qualified leads get a personalized cold email draft from a pricier,
   higher-quality model (Sonnet 4.6).
5. A cohort of qualified leads with drafts surfaces for human review:
   approve, edit, or reject each one.
6. Approved leads export to CSV (business data + email draft + qualification
   metadata). No email sending is built in — the CSV is the handoff artifact.

## Features

### Lead Generation

- Prompt-to-search-query parsing via a DSPy typed signature
- Google Maps search via the MCP bridge (SerpAPI or `google_places` provider)
- Per-lead parallel enrich → qualify → email pipeline

### Qualification & Drafting

- ICP-fit qualification (Haiku 4.5) with structured `is_qualified` / `score`
  / `reasoning` / `icp_fit` output
- Personalized email drafting (Sonnet 4.6), constrained by a DSPy signature
  (80-char subject, 200-word body)

### Review & Export

- Human approval cohort UI: approve / edit / reject per lead
- CSV export of approved leads

### Observability & Evals

- Langfuse tracing across both the sync (Cloud Run demo) and Temporal
  (local) execution paths
- Promptfoo + DSPy evals for qualifier/email model comparisons (see
  `docs/model-choices.md`)

## Scope

### In Scope

- Everything under Features above
- Local full stack via Docker Compose (Temporal, Postgres, Langfuse)
- Cloud Run public demo running the sync execution path
- Terraform infra for GCP deployment (in progress — `docs/roadmap.md` #1)
- Gemini migration for qualifier/email models, gated on an eval comparison
  against Haiku/Sonnet (`docs/roadmap.md` #2)

### Out of Scope

- Authentication, user accounts, multi-tenancy
- Billing / Stripe / paid tiers
- Actual email sending, domain warming, deliverability monitoring
- CRM features, persistent per-user run history beyond the current session
- Multi-region deployment

These are explicitly deferred to `docs/roadmap.md` §5 ("Full application:
auth, accounts, persistence" — long-term, not started, blocked on the
near-term roadmap items being stable first).

## Success Criteria

1. A user can submit an ICP prompt and receive a reviewed cohort of
   qualified leads with drafted emails within the pipeline's cost/time
   budget.
2. Both orchestration paths (sync demo, Temporal local) produce identical
   business results, since both call the same `pipeline.py` /
   `agent_graph.py` leaf logic.
3. Approved leads export to CSV with business data, email draft, and
   qualification metadata intact.
4. The public demo runs within Cloud Run free-tier constraints (20 runs/day
   cap, 60s request timeout, 25 leads max per run).
