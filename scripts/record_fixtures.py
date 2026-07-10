#!/usr/bin/env python3
"""Record Google Places API fixtures for the demo mock provider.

This script makes REAL, BILLABLE API calls to the Google Places API (New).
DO NOT run it in CI. Run it manually (with --dry-run first) when you need
to refresh the demo fixture data.

Usage:
    python scripts/record_fixtures.py --dry-run
    python scripts/record_fixtures.py --max-calls 50

Each query costs 2 calls at minimum (1 Text Search + at least 1 Details).
With 6 default queries x up to 5 results each: ~36 calls worst-case.
The Google Places API (New) free tier is 5,000 Pro-tier calls/month.
This script stays well under 1% of that.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup — allow running from the repo root without installing packages
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from maps_bridge.providers.google_places import GooglePlacesProvider  # noqa: E402
from shared.schemas import PlaceDetails, PlaceSearchResult  # noqa: E402

# ---------------------------------------------------------------------------
# Default query set — B2B-adjacent Polish SMB categories
# ---------------------------------------------------------------------------
DEFAULT_QUERIES: list[tuple[str, int]] = [
    ("dental clinics Wrocław", 5),
    ("marketing agencies Wrocław", 5),
    ("dental clinics Warszawa", 5),
    ("marketing agencies Kraków", 5),
    ("accounting firms Wrocław", 5),
    ("law firms Warszawa", 5),
]

OUTPUT_DIR = _REPO_ROOT / "maps_bridge" / "fixtures" / "recorded"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _slug(text: str) -> str:
    """Convert a query string to a safe filename slug."""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _estimate_calls(queries: list[tuple[str, int]]) -> int:
    """Return upper-bound call estimate: 1 search + limit details per query."""
    return sum(1 + limit for _, limit in queries)


def _assert_no_key_in_file(path: Path, api_key: str) -> None:
    """Raise if the API key string appears anywhere in the written file."""
    if api_key and api_key in path.read_text(encoding="utf-8"):
        path.unlink()
        raise RuntimeError(
            f"ABORT: API key found in {path} — file deleted. "
            "Check that the provider is not embedding credentials in responses."
        )


# ---------------------------------------------------------------------------
# Recording logic
# ---------------------------------------------------------------------------


async def record(
    queries: list[tuple[str, int]],
    api_key: str,
    max_calls: int,
    dry_run: bool,
    verbose: bool,
) -> None:
    estimated = _estimate_calls(queries)
    print(f"\nQueries to record ({len(queries)} total, ~{estimated} API calls):")
    for q, limit in queries:
        print(f"  '{q}'  (limit={limit}, ~{1 + limit} calls)")

    if dry_run:
        print("\n[DRY RUN] No API calls will be made.")
        print(f"[DRY RUN] Would write to: {OUTPUT_DIR}")
        return

    if estimated > max_calls:
        print(
            f"\nABORT: estimated {estimated} calls exceeds --max-calls {max_calls}. "
            "Lower the number of queries/limits or raise --max-calls."
        )
        sys.exit(1)

    answer = input(
        f"\nThis will make up to ~{estimated} billable API calls "
        f"against your Google Places API key. Continue? [y/N] "
    )
    if answer.strip().lower() != "y":
        print("Aborted.")
        sys.exit(0)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "search").mkdir(exist_ok=True)
    (OUTPUT_DIR / "details").mkdir(exist_ok=True)

    provider = GooglePlacesProvider(api_key=api_key)
    call_count = 0
    manifest: list[dict[str, object]] = []

    for query, limit in queries:
        slug = _slug(query)
        print(f"\n[{call_count}/{estimated}] search_places('{query}', {limit}) …")

        if call_count + 1 > max_calls:
            print(f"ABORT: --max-calls {max_calls} reached before completing all queries.")
            _write_manifest(manifest)
            sys.exit(1)

        results: list[PlaceSearchResult] = await provider.search_places(query, limit)
        call_count += 1
        print(f"  → {len(results)} results (call #{call_count})")

        search_file = OUTPUT_DIR / "search" / f"{slug}.json"
        search_file.write_text(
            json.dumps(
                [json.loads(r.model_dump_json()) for r in results], indent=2, ensure_ascii=False
            ),
            encoding="utf-8",
        )
        _assert_no_key_in_file(search_file, api_key)

        detail_ids: list[str] = []
        for result in results:
            if call_count + 1 > max_calls:
                print(
                    f"  WARN: --max-calls {max_calls} reached — skipping remaining details for '{query}'."
                )
                break

            if verbose:
                print(f"  get_place_details('{result.id}') …")

            details: PlaceDetails = await provider.get_place_details(result.id)
            call_count += 1
            if verbose:
                print(f"    → {details.name} (call #{call_count})")

            details_file = OUTPUT_DIR / "details" / f"{result.id}.json"
            details_file.write_text(
                details.model_dump_json(indent=2),
                encoding="utf-8",
            )
            _assert_no_key_in_file(details_file, api_key)
            detail_ids.append(result.id)

        manifest.append(
            {
                "query": query,
                "slug": slug,
                "limit": limit,
                "result_count": len(results),
                "detail_ids": detail_ids,
            }
        )

    _write_manifest(manifest, call_count)
    print(f"\nDone. {call_count} API calls made. Fixtures written to {OUTPUT_DIR}")


def _write_manifest(manifest: list[dict[str, object]], call_count: int = 0) -> None:
    manifest_data = {
        "recorded_at": datetime.now(tz=UTC).isoformat(),
        "total_calls": call_count,
        "queries": manifest,
    }
    manifest_file = OUTPUT_DIR / "manifest.json"
    manifest_file.write_text(
        json.dumps(manifest_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Manifest written to {manifest_file}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan and exit — no API calls, no files written.",
    )
    parser.add_argument(
        "--max-calls",
        type=int,
        default=100,
        metavar="N",
        help="Hard limit on total API calls. Script aborts if it would exceed this. Default: 100.",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print each place_id as it is fetched.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    api_key = os.environ.get("GOOGLE_MAPS_API_KEY", "")
    if not api_key and not args.dry_run:
        print("ERROR: GOOGLE_MAPS_API_KEY is not set.", file=sys.stderr)
        print("Set it in your shell: export GOOGLE_MAPS_API_KEY=<your-key>", file=sys.stderr)
        sys.exit(1)

    asyncio.run(
        record(
            queries=DEFAULT_QUERIES,
            api_key=api_key,
            max_calls=args.max_calls,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
    )


if __name__ == "__main__":
    main()
