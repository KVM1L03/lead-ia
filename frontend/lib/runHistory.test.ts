import { describe, expect, it } from "vitest";
import { approvalRate, formatRelativeTime, isTerminal, statusConfig } from "./runHistory";

// ── formatRelativeTime ────────────────────────────────────────────────────────

describe("formatRelativeTime", () => {
  function at(offsetMs: number): { date: Date; now: Date } {
    const now = new Date("2025-01-15T12:00:00Z");
    const date = new Date(now.getTime() - offsetMs);
    return { date, now };
  }

  it("< 60s → 'just now'", () => {
    const { date, now } = at(30_000);
    expect(formatRelativeTime(date, now)).toBe("just now");
  });

  it("1 minute → singular", () => {
    const { date, now } = at(61_000);
    expect(formatRelativeTime(date, now)).toBe("1 minute ago");
  });

  it("45 minutes → plural", () => {
    const { date, now } = at(45 * 60_000);
    expect(formatRelativeTime(date, now)).toBe("45 minutes ago");
  });

  it("1 hour → singular", () => {
    const { date, now } = at(60 * 60_000 + 1_000);
    expect(formatRelativeTime(date, now)).toBe("1 hour ago");
  });

  it("3 hours → plural", () => {
    const { date, now } = at(3 * 60 * 60_000);
    expect(formatRelativeTime(date, now)).toBe("3 hours ago");
  });

  it("1 day → singular", () => {
    const { date, now } = at(25 * 60 * 60_000);
    expect(formatRelativeTime(date, now)).toBe("1 day ago");
  });

  it("7 days → plural", () => {
    const { date, now } = at(7 * 24 * 60 * 60_000);
    expect(formatRelativeTime(date, now)).toBe("7 days ago");
  });

  it(">= 30 days → formatted date", () => {
    const { date, now } = at(31 * 24 * 60 * 60_000);
    const result = formatRelativeTime(date, now);
    expect(result).toMatch(/Dec|Jan|2024|2025/);
    expect(result).not.toContain("ago");
  });
});

// ── approvalRate ──────────────────────────────────────────────────────────────

describe("approvalRate", () => {
  it("0 total → null (no divide by zero)", () => {
    expect(approvalRate(0, 0)).toBeNull();
  });

  it("none approved → 0", () => {
    expect(approvalRate(0, 10)).toBe(0);
  });

  it("all approved → 1", () => {
    expect(approvalRate(5, 5)).toBe(1);
  });

  it("partial → fractional", () => {
    expect(approvalRate(3, 10)).toBeCloseTo(0.3);
  });
});

// ── statusConfig ──────────────────────────────────────────────────────────────

describe("statusConfig", () => {
  it("completed → green label", () => {
    const cfg = statusConfig("completed");
    expect(cfg.label).toBe("Completed");
    expect(cfg.className).toContain("emerald");
  });

  it("failed → red label", () => {
    const cfg = statusConfig("failed");
    expect(cfg.label).toBe("Failed");
    expect(cfg.className).toContain("red");
  });

  it("scraping → amber in-progress label", () => {
    const cfg = statusConfig("scraping");
    expect(cfg.label).toBe("Scraping");
    expect(cfg.className).toContain("amber");
  });

  it("qualifying → amber in-progress label", () => {
    const cfg = statusConfig("qualifying");
    expect(cfg.label).toBe("Qualifying");
    expect(cfg.className).toContain("amber");
  });

  it("generating → amber in-progress label", () => {
    const cfg = statusConfig("generating");
    expect(cfg.label).toBe("Generating");
    expect(cfg.className).toContain("amber");
  });

  it("unknown status → falls back gracefully", () => {
    const cfg = statusConfig("pending");
    expect(cfg.label).toBe("pending");
    expect(cfg.className).toContain("slate");
  });
});

// ── isTerminal ────────────────────────────────────────────────────────────────

describe("isTerminal", () => {
  it("completed is terminal", () => expect(isTerminal("completed")).toBe(true));
  it("failed is terminal", () => expect(isTerminal("failed")).toBe(true));
  it("scraping is not terminal", () => expect(isTerminal("scraping")).toBe(false));
  it("qualifying is not terminal", () => expect(isTerminal("qualifying")).toBe(false));
  it("generating is not terminal", () => expect(isTerminal("generating")).toBe(false));
});
