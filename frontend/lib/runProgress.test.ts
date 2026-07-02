import { describe, expect, it } from "vitest";
import {
  computeStages,
  synthesizeEvents,
  type ProgressSnapshot,
} from "./runProgress";

// ── computeStages ─────────────────────────────────────────────────────────────

describe("computeStages", () => {
  const prog = { scraped: 0, qualified: 0, emails_generated: 0 };

  it("all pending before scraping starts", () => {
    const stages = computeStages("scraping", prog, 20);
    expect(stages[0].state).toBe("active");
    expect(stages[1].state).toBe("pending");
    expect(stages[2].state).toBe("pending");
  });

  it("stage 1 done, stage 2 active during qualifying", () => {
    const p = { scraped: 15, qualified: 3, emails_generated: 0 };
    const stages = computeStages("qualifying", p, 20);
    expect(stages[0].state).toBe("done");
    expect(stages[1].state).toBe("active");
    expect(stages[2].state).toBe("pending");
  });

  it("stages 1+2 done, stage 3 active during generating", () => {
    const p = { scraped: 15, qualified: 7, emails_generated: 2 };
    const stages = computeStages("generating", p, 20);
    expect(stages[0].state).toBe("done");
    expect(stages[1].state).toBe("done");
    expect(stages[2].state).toBe("active");
  });

  it("all done when completed", () => {
    const p = { scraped: 15, qualified: 7, emails_generated: 7 };
    const stages = computeStages("completed", p, 20);
    expect(stages.every((s) => s.state === "done")).toBe(true);
  });

  it("all done when failed", () => {
    const stages = computeStages("failed", prog, 20);
    expect(stages.every((s) => s.state === "done")).toBe(true);
  });

  it("stage 1 progress tracks scraped/limit", () => {
    const p = { scraped: 8, qualified: 0, emails_generated: 0 };
    const stages = computeStages("scraping", p, 20);
    expect(stages[0].current).toBe(8);
    expect(stages[0].total).toBe(20);
  });

  it("stage 2 total falls back to limit when scraped=0", () => {
    const stages = computeStages("scraping", prog, 20);
    expect(stages[1].total).toBe(20);
  });
});

// ── synthesizeEvents ──────────────────────────────────────────────────────────

describe("synthesizeEvents", () => {
  const base: ProgressSnapshot = {
    status: "scraping",
    scraped: 0,
    qualified: 0,
    emails_generated: 0,
  };

  it("emits nothing when nothing changed", () => {
    expect(synthesizeEvents(base, base)).toHaveLength(0);
  });

  it("emits scraping progress event", () => {
    const next = { ...base, scraped: 5 };
    const evs = synthesizeEvents(base, next);
    expect(evs).toHaveLength(1);
    expect(evs[0]).toContain("5 places");
  });

  it("emits stage transition to qualifying", () => {
    const prev = { ...base, scraped: 15 };
    const next: ProgressSnapshot = { status: "qualifying", scraped: 15, qualified: 0, emails_generated: 0 };
    const evs = synthesizeEvents(prev, next);
    expect(evs[0]).toMatch(/15 places.*qualifying/i);
  });

  it("emits stage transition to generating", () => {
    const prev: ProgressSnapshot = { status: "qualifying", scraped: 15, qualified: 7, emails_generated: 0 };
    const next: ProgressSnapshot = { status: "generating", scraped: 15, qualified: 7, emails_generated: 0 };
    const evs = synthesizeEvents(prev, next);
    expect(evs[0]).toMatch(/7 leads.*drafting/i);
  });

  it("emits completion event", () => {
    const prev: ProgressSnapshot = { status: "generating", scraped: 15, qualified: 7, emails_generated: 7 };
    const next: ProgressSnapshot = { status: "completed", scraped: 15, qualified: 7, emails_generated: 7 };
    const evs = synthesizeEvents(prev, next);
    expect(evs[0]).toMatch(/done/i);
    expect(evs[0]).toContain("7");
  });

  it("emits failed event", () => {
    const next: ProgressSnapshot = { status: "failed", scraped: 5, qualified: 0, emails_generated: 0 };
    const evs = synthesizeEvents(base, next);
    expect(evs[0]).toMatch(/failed/i);
  });
});
