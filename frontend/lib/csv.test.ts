import { describe, it, expect } from "vitest";
import { leadsToCSV } from "./csv";
import type { Lead } from "./api";

const PLACE = {
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
};

const VERDICT = {
  is_qualified: true,
  score: 0.9,
  reasoning: "Good ICP fit.",
  icp_fit: { is_b2b: true },
};

const EMAIL = {
  subject: "Quick question",
  body: "Hi — we help dental clinics.",
  personalization_hooks: ["4.7 stars", "Łódź"],
  model_used: "haiku",
};

const APPROVED_LEAD: Lead = {
  place: PLACE,
  verdict: VERDICT,
  email: EMAIL,
  decision: "approved",
  decided_at: null,
  error: null,
};

describe("leadsToCSV", () => {
  it("emits header row with all 12 columns", () => {
    const csv = leadsToCSV([]);
    const header = csv.split("\r\n")[0];
    expect(header).toBe(
      "business_name,address,website,phone,category,rating,review_count,qualifier_score,qualifier_reasoning,email_subject,email_body,personalization_hooks",
    );
  });

  it("maps an approved lead to correct CSV values", () => {
    const csv = leadsToCSV([APPROVED_LEAD]);
    const rows = csv.trim().split("\r\n");
    expect(rows).toHaveLength(2);
    expect(rows[1]).toContain("Stomatologia Łódź");
    expect(rows[1]).toContain("0.9");
    expect(rows[1]).toContain("dental");
  });

  it("excludes pending and rejected leads", () => {
    const pending: Lead = { ...APPROVED_LEAD, decision: "pending" };
    const rejected: Lead = { ...APPROVED_LEAD, decision: "rejected" };
    const csv = leadsToCSV([pending, rejected, APPROVED_LEAD]);
    const rows = csv.trim().split("\r\n");
    expect(rows).toHaveLength(2); // header + approved only
  });

  it("quotes email body containing commas and newlines", () => {
    const lead: Lead = {
      ...APPROVED_LEAD,
      email: { ...EMAIL, body: 'Hello,\nHow are "you"?' },
    };
    const csv = leadsToCSV([lead]);
    expect(csv).toContain('"Hello,\nHow are ""you""?"');
  });

  it("outputs empty cells for null rating and review_count", () => {
    const lead: Lead = {
      ...APPROVED_LEAD,
      place: { ...PLACE, rating: null, review_count: null },
    };
    const csv = leadsToCSV([lead]);
    const dataRow = csv.trim().split("\r\n")[1];
    expect(dataRow).toContain("dental,,"); // rating and review_count both empty
  });

  it("does not throw for null verdict and email", () => {
    const lead: Lead = { ...APPROVED_LEAD, verdict: null, email: null };
    expect(() => leadsToCSV([lead])).not.toThrow();
  });

  it("joins personalization_hooks with semicolon and space", () => {
    const csv = leadsToCSV([APPROVED_LEAD]);
    expect(csv).toContain("4.7 stars; Łódź");
  });

  it("returns header-only row when leads array is empty", () => {
    const csv = leadsToCSV([]);
    const rows = csv.trim().split("\r\n");
    expect(rows).toHaveLength(1);
  });
});
