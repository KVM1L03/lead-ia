import { describe, it, expect } from "vitest";
import { computeSimulatedSnapshot } from "./simulatedProgress";

describe("computeSimulatedSnapshot", () => {
  it("starts in scraping phase", () => {
    const snap = computeSimulatedSnapshot(0, 20);
    expect(snap.status).toBe("scraping");
    expect(snap.scraped).toBeGreaterThanOrEqual(1);
    expect(snap.qualified).toBe(0);
    expect(snap.emails_generated).toBe(0);
  });

  it("moves to qualifying after scrape phase", () => {
    const snap = computeSimulatedSnapshot(6_000, 20);
    expect(snap.status).toBe("qualifying");
    expect(snap.scraped).toBe(20);
    expect(snap.qualified).toBeGreaterThanOrEqual(1);
  });

  it("moves to generating after qualify phase", () => {
    const snap = computeSimulatedSnapshot(16_000, 20);
    expect(snap.status).toBe("generating");
    expect(snap.emails_generated).toBeGreaterThanOrEqual(0);
  });

  it("never exceeds the requested limit for scraped count", () => {
    const snap = computeSimulatedSnapshot(100_000, 15);
    expect(snap.scraped).toBeLessThanOrEqual(15);
  });
});
