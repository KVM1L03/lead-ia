import { describe, expect, it } from "vitest";
import type { Lead } from "./api";
import {
  allIndustries,
  cohortStats,
  DEFAULT_FILTERS,
  detectIndustry,
  groupIntoCohorts,
  scoreBucket,
} from "./cohorts";

function makeLead(overrides: Partial<{
  placeId: string;
  category: string;
  score: number;
  qualified: boolean;
  website: string | null;
  phone: string | null;
}>): Lead {
  const { placeId = "p1", category = "dental", score = 0.9, qualified = true, website = "https://x.com", phone = "+1" } = overrides;
  return {
    place: { id: placeId, name: "Test", address: "Addr", lat: 0, lng: 0, category, rating: 4, review_count: 10, website, phone, hours: [], photos: [] },
    verdict: { is_qualified: qualified, score, reasoning: "", icp_fit: {} },
    email: { subject: "Hi", body: "Body text", personalization_hooks: ["hook1"], model_used: "haiku" },
    decision: "pending",
    decided_at: null,
    error: null,
  };
}

// ── scoreBucket ───────────────────────────────────────────────────────────────

describe("scoreBucket", () => {
  it("0.81 → high", () => expect(scoreBucket(0.81)).toBe("high"));
  it("0.80 → mid (boundary is exclusive >0.8)", () => expect(scoreBucket(0.80)).toBe("mid"));
  it("0.5 → mid", () => expect(scoreBucket(0.5)).toBe("mid"));
  it("0.49 → low", () => expect(scoreBucket(0.49)).toBe("low"));
  it("0 → low", () => expect(scoreBucket(0)).toBe("low"));
  it("1 → high", () => expect(scoreBucket(1)).toBe("high"));
});

// ── detectIndustry ────────────────────────────────────────────────────────────

describe("detectIndustry", () => {
  it("title-cases single word", () => expect(detectIndustry(makeLead({ category: "dental" }))).toBe("Dental"));
  it("title-cases hyphenated", () => expect(detectIndustry(makeLead({ category: "beauty-salon" }))).toBe("Beauty Salon"));
  it("handles underscore", () => expect(detectIndustry(makeLead({ category: "real_estate" }))).toBe("Real Estate"));
  it("empty category → Other", () => expect(detectIndustry(makeLead({ category: "" }))).toBe("Other"));
});

// ── cohortStats ───────────────────────────────────────────────────────────────

describe("cohortStats", () => {
  it("empty leads", () => {
    const s = cohortStats([]);
    expect(s.count).toBe(0);
    expect(s.avgScore).toBe(0);
  });

  it("computes avg score", () => {
    const leads = [makeLead({ score: 0.8 }), makeLead({ score: 0.6 })];
    expect(cohortStats(leads).avgScore).toBeCloseTo(0.7);
  });

  it("computes pctWebsite (1 of 2)", () => {
    const leads = [makeLead({ website: "https://x.com" }), makeLead({ website: null })];
    expect(cohortStats(leads).pctWebsite).toBe(0.5);
  });

  it("computes pctPhone (2 of 2)", () => {
    const leads = [makeLead({ phone: "+1" }), makeLead({ phone: "+2" })];
    expect(cohortStats(leads).pctPhone).toBe(1);
  });
});

// ── groupIntoCohorts ──────────────────────────────────────────────────────────

describe("groupIntoCohorts", () => {
  const leads: Lead[] = [
    makeLead({ placeId: "a", category: "dental", score: 0.9, qualified: true }),
    makeLead({ placeId: "b", category: "dental", score: 0.85, qualified: true }),
    makeLead({ placeId: "c", category: "spa", score: 0.7, qualified: true }),
    makeLead({ placeId: "d", category: "spa", score: 0.4, qualified: true }),
    makeLead({ placeId: "e", category: "dental", score: 0.6, qualified: true }),
    makeLead({ placeId: "f", category: "dental", score: 0.95, qualified: false }),
  ];

  it("excludes unqualified leads", () => {
    const cohorts = groupIntoCohorts(leads);
    const all = cohorts.flatMap((c) => c.leads);
    expect(all.every((l) => l.verdict?.is_qualified === true)).toBe(true);
    expect(all.find((l) => l.place.id === "f")).toBeUndefined();
  });

  it("groups by bucket and industry", () => {
    const cohorts = groupIntoCohorts(leads);
    const labels = cohorts.map((c) => `${c.bucket}::${c.industry}`);
    expect(labels).toContain("high::Dental");
    expect(labels).toContain("mid::Spa");
    expect(labels).toContain("mid::Dental");
    expect(labels).toContain("low::Spa");
  });

  it("sorts high before mid before low", () => {
    const cohorts = groupIntoCohorts(leads);
    const buckets = cohorts.map((c) => c.bucket);
    const highIdx = buckets.indexOf("high");
    const midIdx = buckets.findIndex((b) => b === "mid");
    const lowIdx = buckets.indexOf("low");
    expect(highIdx).toBeLessThan(midIdx);
    expect(midIdx).toBeLessThan(lowIdx);
  });

  it("label includes count", () => {
    const cohorts = groupIntoCohorts(leads);
    const high = cohorts.find((c) => c.bucket === "high")!;
    expect(high.label).toMatch(/2 leads/);
  });

  it("filter by minScore narrows results", () => {
    const cohorts = groupIntoCohorts(leads, { ...DEFAULT_FILTERS, minScore: 0.8 });
    const all = cohorts.flatMap((c) => c.leads);
    expect(all.every((l) => (l.verdict?.score ?? 0) >= 0.8)).toBe(true);
  });

  it("filter hasWebsite=true excludes no-website leads", () => {
    const mixed: Lead[] = [
      makeLead({ placeId: "x", website: "https://x.com", score: 0.9 }),
      makeLead({ placeId: "y", website: null, score: 0.9 }),
    ];
    const cohorts = groupIntoCohorts(mixed, { ...DEFAULT_FILTERS, hasWebsite: true });
    expect(cohorts.flatMap((c) => c.leads).every((l) => l.place.website)).toBe(true);
  });

  it("filter by industry narrows results", () => {
    const cohorts = groupIntoCohorts(leads, { ...DEFAULT_FILTERS, industries: ["Dental"] });
    expect(cohorts.every((c) => c.industry === "Dental")).toBe(true);
  });
});

// ── allIndustries ─────────────────────────────────────────────────────────────

describe("allIndustries", () => {
  it("returns sorted unique industries from qualified leads only", () => {
    const leads: Lead[] = [
      makeLead({ category: "spa", qualified: true }),
      makeLead({ category: "dental", qualified: true }),
      makeLead({ category: "spa", qualified: true }),
      makeLead({ category: "gym", qualified: false }),
    ];
    expect(allIndustries(leads)).toEqual(["Dental", "Spa"]);
  });
});
