import { describe, expect, it } from "vitest";
import { buildExhaustionBannerText } from "./exhaustionBanner";

describe("buildExhaustionBannerText", () => {
  const base = {
    backfillExhausted: false,
    qualified: 85,
    limit: 100,
    triedCities: [] as string[],
    triedIndustries: [] as string[],
  };

  it("renders nothing when backfill_exhausted is false", () => {
    expect(buildExhaustionBannerText(base)).toBeNull();
  });

  it("renders nothing when fields are absent (backward-compat defaults)", () => {
    expect(
      buildExhaustionBannerText({ ...base, backfillExhausted: false, triedCities: [], triedIndustries: [] }),
    ).toBeNull();
  });

  it("names one tried city and one tried industry", () => {
    const text = buildExhaustionBannerText({
      ...base,
      backfillExhausted: true,
      triedCities: ["Krakow"],
      triedIndustries: ["aesthetic dentistry"],
    });
    expect(text).toBe("Found 85/100 — also checked Krakow and 'aesthetic dentistry', no further matches.");
  });

  it("names only tried cities when no industries were tried", () => {
    const text = buildExhaustionBannerText({
      ...base,
      backfillExhausted: true,
      triedCities: ["Krakow"],
      triedIndustries: [],
    });
    expect(text).toBe("Found 85/100 — also checked Krakow, no further matches.");
  });

  it("names only tried industries when no cities were tried", () => {
    const text = buildExhaustionBannerText({
      ...base,
      backfillExhausted: true,
      triedCities: [],
      triedIndustries: ["aesthetic dentistry"],
    });
    expect(text).toBe("Found 85/100 — also checked 'aesthetic dentistry', no further matches.");
  });

  it("Oxford-joins three or more tried items", () => {
    const text = buildExhaustionBannerText({
      ...base,
      backfillExhausted: true,
      triedCities: ["Krakow", "Poznan"],
      triedIndustries: ["aesthetic dentistry"],
    });
    expect(text).toBe(
      "Found 85/100 — also checked Krakow, Poznan, and 'aesthetic dentistry', no further matches.",
    );
  });

  it("falls back to a plain message when exhausted but nothing was tried", () => {
    const text = buildExhaustionBannerText({
      ...base,
      backfillExhausted: true,
      triedCities: [],
      triedIndustries: [],
    });
    expect(text).toBe("Found 85/100 — no further matches found.");
  });
});
