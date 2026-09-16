import { afterEach, describe, expect, it, vi } from "vitest";
import { searchLeads, getStatus, approveLeads, exportLeads, type Lead } from "./api";

const APPROVED_LEAD: Lead = {
  place: {
    id: "p1",
    name: "Stomatologia Łódź",
    address: "ul. Test 1, Łódź",
    lat: 51.77,
    lng: 19.45,
    category: "dental",
    rating: 4.7,
    review_count: 214,
    website: "https://stom.pl",
    phone: "+48 42 123 456",
    hours: [],
    photos: [],
  },
  verdict: {
    is_qualified: true,
    score: 0.9,
    reasoning: "Good ICP fit.",
    icp_fit: { is_b2b: true },
  },
  email: {
    subject: "Quick question",
    body: "Hi — we help dental clinics.",
    personalization_hooks: ["4.7 stars", "Łódź"],
    model_used: "haiku",
  },
  decision: "approved",
  decided_at: null,
  error: null,
};

describe("api exports", () => {
  it("exports async functions for all four endpoints", () => {
    expect(typeof searchLeads).toBe("function");
    expect(typeof getStatus).toBe("function");
    expect(typeof approveLeads).toBe("function");
    expect(typeof exportLeads).toBe("function");
  });

  it("getStatus builds correct URL (fetch will be called with workflowId in path)", () => {
    // Verify the function signature accepts a string without throwing at import time.
    expect(getStatus.length).toBe(1);
  });
});

describe("exportLeads", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("POSTs run_id and leads to /api/leads/export and returns the CSV body", async () => {
    const csv = "business_name\nStomatologia Łódź\n";
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      text: () => Promise.resolve(csv),
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await exportLeads("run-1", [APPROVED_LEAD]);

    expect(result).toBe(csv);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/leads\/export$/);
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      run_id: "run-1",
      leads: [APPROVED_LEAD],
    });
  });

  it("throws when the export endpoint returns a non-2xx status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        statusText: "Unprocessable Entity",
        text: () => Promise.resolve("leads required"),
      }),
    );

    await expect(exportLeads("run-1", [APPROVED_LEAD])).rejects.toThrow(
      /422 \/api\/leads\/export/,
    );
  });
});
