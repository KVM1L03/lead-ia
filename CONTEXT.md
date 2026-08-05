# LeadForge

Prompt → Google Places (via SerpAPI) → cheap-model qualifier → email draft → human approval. Local-first, BYOK, single-user demo.

## Language

**Backfill**:
The reactive loop that runs after qualification leaves the cohort short of the user's requested `limit`. An LLM decides which axis (city or industry) to widen the search on, generates a new search query, and the pipeline re-runs search → qualify on it — repeating until the shortfall closes or a stop condition is hit. Runs only on the Temporal execution path.
_Avoid_: supplement, expand, top-up, gap-fill

**Shortfall**:
The gap between the user's requested `limit` and the number of leads that passed qualification (`is_qualified`) after the original search. This is what triggers a Backfill.

**Strategy axis**:
Which dimension a Backfill round widens on: `city` (neighboring city/region) or `industry` (adjacent business category). Exactly two axes — tracked as separate lists (`tried_cities`, `tried_industries`) so the same value is never retried.
