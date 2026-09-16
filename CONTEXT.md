# LeadForge

Prompt → Google Places (via SerpAPI) → cheap-model qualifier → email draft → human approval. Local-first, BYOK, single-user demo.

## Language

**Backfill**:
The reactive loop that runs after qualification leaves the cohort short of the user's requested `limit`. An LLM decides which axis (city or industry) to widen the search on, generates a new search query, and the pipeline re-runs search → qualify on it — repeating until the shortfall closes or a stop condition is hit. Runs only on the Temporal execution path.
_Avoid_: supplement, expand, top-up, gap-fill

**ICP Criteria**:
The explicit checklist a business is judged against, derived from the prompt before the run starts and approved or edited by the user at Preflight. The same list the qualifier reports on, key by key.
_Avoid_: filters, requirements, rules

**Preflight**:
The confirmation step between writing the prompt and starting a run: the generated Places query and the ICP Criteria, both editable, plus the widening axes allowed for Backfill. Nothing is searched or spent until it is approved.
_Avoid_: preview, dry run, confirmation screen

**Lead origin**:
Which round produced a lead — the original search, or a Backfill round together with the Strategy axis value that widened it.
_Avoid_: source, provenance

**Site Profile**:
The structured view of a business's own website: contact addresses found there, evidence for or against the user's ICP criteria, and a short description. Built for every business found in a run, before qualification, and consumed by qualification, the email draft, and the export.
_Avoid_: scrape, snapshot, enrichment, crawl

**Shortfall**:
The gap between the user's requested `limit` and the number of leads that passed qualification (`is_qualified`) after the original search. This is what triggers a Backfill.

**Contact Ledger**:
The cross-run record of businesses already dealt with and mailboxes already written to. Three outcomes: _contacted_ (approved or exported), _dismissed_ (rejected by hand during review), and _seen_ (surfaced in a run but never decided).
_Avoid_: blacklist, suppression list, CRM

**Suppressed**:
A business or mailbox the Contact Ledger keeps out of a new run — the _contacted_ and _dismissed_ entries, dropped right after search, before any Site Profile or qualification work. A Suppressed business still counts toward the Shortfall, so Backfill makes up for it.
_Avoid_: blocked, filtered, banned

**Strategy axis**:
Which dimension a Backfill round widens on: `city` (neighboring city/region) or `industry` (adjacent business category). Exactly two axes — tracked as separate lists (`tried_cities`, `tried_industries`) so the same value is never retried.
