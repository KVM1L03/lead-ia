# Design: Site Profile, Contact Ledger, and Preflight

Date: 2026-09-16

## Background

A product review of the README against the code found that LeadIA produces a
cohort of qualified businesses with drafted emails that a user cannot actually
act on, and cannot safely run twice. This design closes four gaps; two further
ones (a feedback loop from approve/reject decisions, and a BYOK cost meter)
were explicitly deferred.

Audience decision that bounds everything below: the target user is **one real
operator running locally with their own keys**. No auth, no multi-tenancy, no
billing, no email sending — the out-of-scope list in
`context/project-overview.md` stands. What changes is the bar: the tool has to
work end to end for that one person, not merely demonstrate the architecture.

## Problems

1. **The export cannot be used.** `PlaceDetails` carries `website` and `phone`
   and nothing else; the CSV columns in `api_gateway/routes/export.py` mirror
   that. There is no recipient address anywhere in the pipeline, so "approve →
   send-ready CSV" leaves the user to open every website by hand.
2. **Qualification judges what it cannot see.** `QualifyLead` receives only
   `outreach_goal` and a serialized `PlaceDetails`. The README's own example —
   *dental practices in Warsaw with no online booking* — is therefore scored
   from a name, an address, a category and a rating. The verdicts read
   plausibly and are partly guesses.
3. **A second run repeats the first.** Runs persist, but nothing connects them.
   Overlapping prompts re-surface the same businesses, and Backfill widening by
   city or industry makes overlap the expected case, not the edge case.
4. **The run starts blind and widens silently.** The Places query generated
   from the prompt is never shown before it is spent, and leads found by
   widening to a neighbouring city are merged into the cohort with no marker
   and no way to opt out.

## Decisions (confirmed with user)

### Site Profile

1. **A new `fetch_site` tool in `maps_bridge`** retrieves the business website.
   One network boundary, invariant #5 intact; SSRF handled in code (http/https
   only, private and link-local ranges blocked, size and time limits).
   See [ADR 0003](../../adr/0003-website-fetching-lives-in-maps-bridge.md).
2. **The fetch runs before qualification, for every business found** — one
   fetch feeds qualification, personalization and contact.
   See [ADR 0004](../../adr/0004-site-profile-before-qualification.md).
3. **The page becomes a compact Site Profile via a cheap DSPy extraction**
   steered by the run's ICP Criteria: contact addresses, evidence for and
   against each criterion, and a short description. Raw page text is not
   persisted and never reaches the qualifier prompt directly.
4. **Extracted email addresses are validated before they are trusted.** An
   address must appear verbatim in the fetched content, pass format validation,
   and either match the site's domain or belong to a known mailbox provider.
   Anything that fails is discarded, not shown — a wrong recipient is a silent
   failure, and silence is the expensive kind.
5. **A qualified lead with no address stays in the cohort.** It is reviewable,
   approvable and exportable, with the gap shown plainly, a field for entering
   an address by hand, and the phone number as the fallback channel.
6. **The sync demo serves recorded Site Profiles from the mock fixtures** — no
   fetches, no extra LLM calls, same 60 s budget, and the public demo shows the
   real feature rather than a degraded one.

### Contact Ledger

7. **Three outcomes are remembered across runs:** _contacted_ (approved or
   exported), _dismissed_ (rejected by hand at review), _seen_ (surfaced, never
   decided). Only the first two suppress.
8. **Identity has two levels.** A business is identified by `place_id`; a
   recipient by normalized email address. The second level exists because a
   chain with five branches is five Maps entries and one mailbox — without it
   the same inbox gets five emails from a single run, which no cross-run check
   would catch.
9. **Suppressed entries are dropped immediately after search**, before any
   fetch or qualification, and **count toward the Shortfall** so Backfill makes
   up the difference. The review UI reports how many were skipped and lets the
   user look at them.

### Preflight

10. **A blocking confirmation step before the search runs**, showing the
    generated Places query, the ICP Criteria and the widening axes allowed for
    this run — all editable. Nothing is searched or spent until it is approved.
    Placing it before the search also protects the Places quota from a bad
    query. This requires splitting "translate the prompt" from "start the run",
    which today both happen inside `POST /api/leads/search`.
11. **The ICP Criteria are the qualifier's contract**, not a restatement of the
    prompt: the approved list is what `QualifyLead` checks and what `icp_fit`
    reports on.
    See [ADR 0005](../../adr/0005-icp-criteria-are-an-approved-contract.md).

### Backfill

12. **The user chooses the allowed widening axes** (city, industry, both, off;
    both by default), and **every lead carries its origin** — original search,
    or the Backfill round and axis value that produced it — visible as a badge
    and available as a filter.

## Domain language added to `CONTEXT.md`

`ICP Criteria`, `Preflight`, `Lead origin`, `Site Profile`, `Contact Ledger`,
`Suppressed`. Existing terms (`Backfill`, `Shortfall`, `Strategy axis`) are
unchanged; `Shortfall` now also counts Suppressed businesses.

## Contract shape

Not final signatures — the boundaries each ticket has to respect.

- `shared/schemas.py` gains `SiteProfile` (contact addresses, per-criterion
  evidence, description) and `ICPCriteria`; `Lead` gains `site_profile`,
  `contact_email`, and `origin`.
- `maps_bridge` gains one MCP tool, `fetch_site`, returning fetched text plus
  the final URL — no parsing or LLM work in the bridge.
- `POST /api/leads/plan` (new) returns the query and criteria for approval;
  `POST /api/leads/search` accepts the approved query, criteria and allowed
  axes instead of deriving them.
- CSV export gains a `contact_email` column, positioned before `website`.
- Prisma and SQLAlchemy both gain the Contact Ledger table; the demo path
  (`PERSISTENCE_ENABLED=false`) has no ledger and therefore no suppression.

## Delivery plan

Twelve tickets, each sized for a reviewable PR. Dependencies are strict where
stated; anything unstated can be picked up in parallel.

| # | Ticket | Depends on | Rough size |
|---|---|---|---|
| 1 | `fetch_site` MCP tool: fetch, SSRF guards, HTML → text, tests | — | ~150 |
| 2 | `SiteProfile` schema, `ExtractSiteProfile` signature, address validation | 1 | ~200 |
| 3 | Graph node + Temporal activity + sync path; `Lead.site_profile`; recorded fixtures for the mock provider | 1, 2 | ~250 |
| 4 | Qualify and email consume the Site Profile; eval re-baseline | 3 | ~150 + evals |
| 5 | Contact in the review UI and the CSV: column, manual entry, missing-address state | 3 | ~200 |
| 6 | Contact Ledger persistence: Prisma + SQLAlchemy models, writes on approve / reject / export / seen | 5 | ~200 |
| 7 | Suppression in the pipeline: filter after search, count into Shortfall, skipped-count in the UI | 6 | ~200 |
| 8 | Preflight backend: `POST /api/leads/plan`, criteria on `PromptToQuery`, approved values accepted by `search` | — | ~200 |
| 9 | Preflight UI: confirmation screen with editable query, criteria and axis toggle | 8 | ~250 |
| 10 | ICP Criteria as the qualifier's contract; eval re-baseline | 8 | ~150 + evals |
| 11 | Lead origin: schema field, carried through Backfill rounds, badge and filter in the cohort table | — | ~200 |
| 12 | Docs: README (Backfill in the flow, demo caveat, new capabilities), CHANGELOG, progress tracker, `context/` | 1–11 | docs |

Tickets 4 and 10 both change qualifier behaviour and both need
`make eval` plus the `run-evals` label; landing them back to back keeps the
number of eval baselines to two.

## Out of scope

- Feedback loop from approve / reject / edit decisions into ICP refinement and
  eval data — the strongest remaining product idea, deliberately deferred to
  its own design.
- BYOK cost and quota meter in the UI.
- Responsive layout, real per-lead progress on the sync path, lead-level error
  states (`docs/roadmap.md` #3 and #4).
- Auth, accounts, email sending (`docs/roadmap.md` #5).
- Explicit geographic scope for a run (allow-list of cities or a radius) and
  pausing a run for approval before each widening round — both considered as
  Backfill controls and rejected in favour of the axis toggle.
- Renaming `maps_bridge` now that it fetches more than maps.

## Open questions

- Which mailbox providers count as an acceptable domain mismatch for
  validation — a short built-in list, or configuration?
- Do we honour `robots.txt` for `fetch_site`? Not decided. It costs one extra
  request per host and is the polite default for a tool that fetches sites it
  does not own.
- How the recorded Site Profile fixtures get produced — a one-off live
  recording pass, or hand-written alongside the existing place fixtures.
- Assumed unless someone objects during implementation: when a fetch fails
  (timeout, 403, no website at all), the lead is qualified from Places data
  alone and the Site Profile is marked unavailable, rather than the lead being
  dropped.
- Whether the Contact Ledger needs a reset or "forget this business" action in
  the UI before it is useful — likely yes after a few weeks of real use.
