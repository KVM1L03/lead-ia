# scripts/

Utility scripts for one-off developer tasks. None of these run in CI.

---

## record_fixtures.py

Records real Google Places API responses into `maps_bridge/fixtures/recorded/`
for use by the demo mock provider.

### What it does

For each query in `DEFAULT_QUERIES`, the script calls:

1. `GooglePlacesProvider.search_places(query, limit)` — 1 call per query
2. `GooglePlacesProvider.get_place_details(place_id)` — 1 call per result

Results are serialized via the Pydantic models (`PlaceSearchResult` /
`PlaceDetails`) and written as pretty-printed JSON so fixture diffs are
readable in git.

Output layout:

```
maps_bridge/fixtures/recorded/
  manifest.json                    ← recorded_at timestamp + query index
  search/
    dental_clinics_wroc_aw.json    ← list[PlaceSearchResult]
    marketing_agencies_wroc_aw.json
    …
  details/
    ChIJxxxxxxxxxxxxxxxx.json      ← PlaceDetails per place_id
    …
```

### Cost

Default query set: 6 queries × up to 5 results each.

| Item | Count |
|------|-------|
| Text Search calls (Pro tier) | 6 |
| Place Details calls (Advanced tier) | up to 30 |
| **Total worst-case** | **~36 calls** |

Google Places API (New) free tier: **5,000 Pro calls/month** (Text Search),
**? Advanced calls/month** (Place Details has a separate free allocation).
36 calls is well under 1% of the monthly free tier.

These are the same FieldMasks as production (`_SEARCH_MASK` / `_DETAILS_MASK`
in `google_places.py`) — no rating fields, no atmosphere fields, so the
billing tier stays at Pro/Advanced, not Enterprise.

### Prerequisites

```bash
export GOOGLE_MAPS_API_KEY=<your-key>
# Key must have: billing enabled, Places API (New) activated.
# See .env.example for the full setup checklist.
```

### How to run

**Always do a dry run first:**

```bash
python scripts/record_fixtures.py --dry-run
```

This prints the plan and estimated call count, then exits. No network calls,
no files written.

**When you're satisfied, run for real:**

```bash
python scripts/record_fixtures.py --max-calls 50
```

The script will print the estimated call count and ask for explicit
confirmation before making any calls. `--max-calls` is a hard ceiling —
the script aborts if it would exceed it.

**Verbose mode** (prints each place_id as it is fetched):

```bash
python scripts/record_fixtures.py --verbose
```

### When to re-run

Rarely. The fixture data is committed to git deliberately — it is the demo's
data source. Re-run only when:

- You want to add or change the query categories
- Recorded fixture data has become stale (businesses have closed, moved, etc.)
- You are testing a new category of B2B leads

### Safety notes

- **Confirmation required.** The script always prints the estimated call count
  and waits for `y` before making any calls.
- **`--max-calls` is a hard limit.** The script aborts mid-run if it would
  exceed it. Default is 100 — well above the default query set (~36).
- **`--dry-run` makes zero API calls.** No files are written either.
- **API key safety.** The script asserts that your `GOOGLE_MAPS_API_KEY`
  value does not appear in any written fixture file. If it does, the file is
  deleted and the script aborts.
- **Fixtures go to `recorded/`**, separate from the hand-written
  `places.json` until T-RR.2 decides what replaces what.
