# LeadIA — Describe your ideal customer. Get qualified leads with drafted emails.

<p align="center">
  <img src="docs/assets/leadia-banner.png" alt="LeadIA — Find high-intent leads on autopilot.">
</p>

<p align="center">
  <a href="https://github.com/KVM1L03/lead-ia/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/KVM1L03/lead-ia/ci.yml?branch=main&style=flat-square&label=ci" alt="CI status"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.12-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12"></a>
  <a href="https://nextjs.org/"><img src="https://img.shields.io/badge/next.js-16-000000?style=flat-square&logo=next.js&logoColor=white" alt="Next.js 16"></a>
  <a href="https://temporal.io/"><img src="https://img.shields.io/badge/temporal-durable-000000?style=flat-square&logo=temporal&logoColor=white" alt="Temporal"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-PolyForm_NC-blue?style=flat-square" alt="License: PolyForm Noncommercial"></a>
</p>

LeadIA is an agentic B2B prospecting pipeline. Describe your ideal customer in one sentence — it searches Google Maps, qualifies every business against your ICP, drafts a personalized cold email for each fit, and stops at the point where judgment matters: you approve, edit, or reject before anything leaves the tool.

**Built to be durable and auditable.** Every external call runs as a Temporal activity with its own timeout and retry policy. Every LLM task is a typed DSPy signature, traced in Langfuse. The agent never touches the network directly — all Maps access goes through a zero-trust MCP bridge. Bring your own keys; everything runs locally with Docker Compose.

[Live demo](https://lead-ia-ten.vercel.app) · [Engineering decisions](docs/engineering-decisions.md) · [Evaluation](docs/engineering-decisions.md#evaluation) · [Changelog](CHANGELOG.md) · [Roadmap](docs/roadmap.md)

> [!NOTE]
> The live demo replays **recorded** Google Places responses and runs the pipeline synchronously, so the first load may take 5–10 s. Clone and run locally with your own key for live search.

## Quick start

Requires Docker, Python 3.12+ with [`uv`](https://docs.astral.sh/uv/), and Node 20+.

```bash
git clone https://github.com/KVM1L03/lead-ia && cd lead-ia
make bootstrap        # install deps, copy .env.example → .env
# add ANTHROPIC_API_KEY to .env (MAPS_PROVIDER=mock needs no Maps key)
make up-build         # Temporal, Langfuse, Postgres, api-gateway, ai-worker
make db-push          # Prisma schema → Postgres
make frontend         # → http://localhost:3000
```

Next.js does not read the root `.env` — create `frontend/.env.local` with `PRISMA_DATABASE_URL`, `NEXT_PUBLIC_API_URL`, `EXECUTION_MODE`, and `PERSISTENCE_ENABLED`. [`.env.example`](.env.example) is the canonical reference, including Langfuse secrets and the live Maps providers.

| Service       | URL                        |
| ------------- | -------------------------- |
| App           | http://localhost:3000      |
| API (Swagger) | http://localhost:8000/docs |
| Temporal UI   | http://localhost:8085      |
| Langfuse      | http://localhost:3030      |

## How it works

```
"dental practices in Warsaw with no online booking"
  → search Google Maps       25 places found
  → qualify against the ICP  14 fits, decided by Jev and reasoned by Haiku 4.5
  → draft cold emails        14 personalized drafts (Sonnet 4.6)
  → human review             you approve 9 → CSV export
```

- **`api_gateway`** (FastAPI) turns the prompt into a Maps query and starts the workflow.
- **`ai_worker`** runs `LeadGenerationWorkflow` on Temporal; a LangGraph graph (`qualify → decide → email`) handles each lead, one activity per node. When a cohort falls short of the target, **Backfill** widens the search by city or industry, up to two rounds.
- **`maps_bridge`** is an MCP server — the only process that calls SerpAPI or the Google Places API.
- **`frontend`** (Next.js 16, Prisma) is the approval UI: live run progress, lead review, run history, CSV export.

Two orchestration paths share the same per-lead logic: `EXECUTION_MODE=temporal` for the durable local stack, and `EXECUTION_MODE=sync` for the scale-to-zero public demo.

## Guardrails

Nothing is sent automatically — approval produces a CSV of send-ready drafts, not outbound email. Qualification results that don't fit the ICP stay in the run record and are never emailed.

Cost is bounded by design: a tight Google Places FieldMask keeps Text Search on the free Pro tier, the MCP bridge caches responses for 24 h, and demo mode enforces a daily run cap, per-IP rate limits, and a 25-lead ceiling. See [`docs/cost-guardrails.md`](docs/cost-guardrails.md).

## Documentation

| Goal                                  | Start here                                                                                                   |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| Understand the design trade-offs      | [Engineering decisions](docs/engineering-decisions.md)                                                       |
| See how models were picked and scored | [Model choices](docs/model-choices.md) · [Evaluation](docs/engineering-decisions.md#evaluation) · [`evals/`](evals/) |
| Understand the product and architecture | [`context/`](context/) · [ADRs](docs/adr/)                                                                   |
| Deploy or audit the deployment        | [Twelve-factor audit](docs/twelve-factor-audit.md) · [`infra/terraform/`](infra/terraform/)                   |
| Follow releases and plans             | [Changelog](CHANGELOG.md) · [Roadmap](docs/roadmap.md)                                                        |
| Work in this repo with an AI agent    | [`AGENTS.md`](AGENTS.md) · [`CLAUDE.md`](CLAUDE.md)                                 |

## Development

```bash
make lint       # ruff + mypy + eslint (same checks as CI)
make test       # pytest + vitest
make eval       # promptfoo eval suite (~$0.10, real API)
make logs       # tail compose logs
make down       # stop, volumes preserved
```

Every change lands through a pull request. CI runs lint and tests on each PR, and a human reviews before merge (see [ADR 0007](docs/adr/0007-remove-automated-llm-diff-review.md) for why there's no automated diff review). **LeadForge** is the internal codename you'll see in `context/` and the compose service names.

## License

[PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/) — free for noncommercial use, study, and modification. Commercial use requires a separate license: **klabusit@gmail.com**.

© 2026 Kamil Labus
