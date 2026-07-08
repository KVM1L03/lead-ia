import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExportCsvButton } from "./ExportCsvButton";
import type { Lead } from "@/lib/api";

// vi.mock is hoisted — "use server" in actions.ts is never evaluated in tests.
vi.mock("@/app/actions", () => ({
  serverExportLeads: vi.fn(),
  startSearch: vi.fn(),
  deleteRun: vi.fn(),
  serverApproveLeads: vi.fn(),
}));

const { serverExportLeads } = await import("@/app/actions");
const mockServerExportLeads = vi.mocked(serverExportLeads);

// ── Fixture ───────────────────────────────────────────────────────────────────

const _APPROVED_LEAD: Lead = {
  place: {
    id: "place-001",
    name: "Stomatologia Łódź",
    address: "ul. Piotrkowska 1, Łódź",
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
    personalization_hooks: ["4.7 stars"],
    model_used: "mock/test",
  },
  decision: "approved",
  decided_at: null,
  error: null,
};

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("ExportCsvButton", () => {
  const onError = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    // jsdom has no URL.createObjectURL — stub it
    URL.createObjectURL = vi.fn(() => "blob:mock-url");
    URL.revokeObjectURL = vi.fn();
    // jsdom cannot handle anchor navigation — suppress the expected noise
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  });

  it("is disabled when approvedLeads is empty", () => {
    render(
      <ExportCsvButton runId="run-1" approvedLeads={[]} onError={onError} />,
    );
    expect(screen.getByRole("button", { name: /export csv/i })).toBeDisabled();
  });

  it("shows tooltip when disabled", () => {
    render(
      <ExportCsvButton runId="run-1" approvedLeads={[]} onError={onError} />,
    );
    expect(screen.getByRole("button", { name: /export csv/i })).toHaveAttribute(
      "title",
      "Approve at least one lead to export",
    );
  });

  it("is enabled when there is at least one approved lead", () => {
    render(
      <ExportCsvButton
        runId="run-1"
        approvedLeads={[_APPROVED_LEAD]}
        onError={onError}
      />,
    );
    expect(screen.getByRole("button", { name: /export csv/i })).not.toBeDisabled();
  });

  it("calls serverExportLeads with runId and approvedLeads on click", async () => {
    mockServerExportLeads.mockResolvedValueOnce({
      ok: true,
      csv: "business_name\nStomatologia Łódź",
    });

    render(
      <ExportCsvButton
        runId="run-1"
        approvedLeads={[_APPROVED_LEAD]}
        onError={onError}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /export csv/i }));

    await waitFor(() => {
      expect(mockServerExportLeads).toHaveBeenCalledWith("run-1", [_APPROVED_LEAD]);
    });
    await waitFor(() => {
      expect(URL.createObjectURL).toHaveBeenCalled();
    });
  });

  it("calls onError and does not throw when serverExportLeads returns ok: false", async () => {
    mockServerExportLeads.mockResolvedValueOnce({
      ok: false,
      error: "Export failed — please try again.",
    });

    render(
      <ExportCsvButton
        runId="run-1"
        approvedLeads={[_APPROVED_LEAD]}
        onError={onError}
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: /export csv/i }));

    await waitFor(() => {
      expect(onError).toHaveBeenCalledWith("Export failed — please try again.");
    });
    expect(URL.createObjectURL).not.toHaveBeenCalled();
  });
});
