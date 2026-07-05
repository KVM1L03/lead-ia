import type { ProgressSnapshot } from "@/lib/runProgress";

/** Phase durations for the sync-pipeline loading simulation (ms). */
const SCRAPE_MS = 5_000;
const QUALIFY_MS = 10_000;
const GENERATE_MS = 20_000;

/**
 * Produce a fake progress snapshot that advances over time while the sync
 * pipeline HTTP request is in flight. Counts ease toward plausible targets
 * so the overlay feels alive without implying real backend telemetry.
 */
export function computeSimulatedSnapshot(
  elapsedMs: number,
  limit: number,
): ProgressSnapshot {
  const scrapedTarget = limit;

  if (elapsedMs < SCRAPE_MS) {
    const t = easeOut(elapsedMs / SCRAPE_MS);
    return {
      status: "scraping",
      scraped: Math.max(1, Math.round(t * scrapedTarget)),
      qualified: 0,
      emails_generated: 0,
    };
  }

  const qualifyElapsed = elapsedMs - SCRAPE_MS;
  if (qualifyElapsed < QUALIFY_MS) {
    const t = easeOut(qualifyElapsed / QUALIFY_MS);
    const qualifiedTarget = Math.max(1, Math.round(scrapedTarget * 0.55));
    return {
      status: "qualifying",
      scraped: scrapedTarget,
      qualified: Math.max(1, Math.round(t * qualifiedTarget)),
      emails_generated: 0,
    };
  }

  const generateElapsed = elapsedMs - SCRAPE_MS - QUALIFY_MS;
  const t = easeOut(Math.min(1, generateElapsed / GENERATE_MS));
  const qualified = Math.max(1, Math.round(scrapedTarget * 0.55));
  return {
    status: "generating",
    scraped: scrapedTarget,
    qualified,
    emails_generated: Math.max(0, Math.round(t * qualified)),
  };
}

function easeOut(t: number): number {
  return 1 - (1 - t) ** 2;
}
