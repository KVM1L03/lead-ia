import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LeadCohortTable } from "./LeadCohortTable";
import type { Lead } from "@/lib/api";

// vi.mock is hoisted — "use server" in actions.ts is never evaluated in tests.
vi.mock("@/app/actions", () => ({
  serverApproveLeads: vi.fn(),
  serverExportLeads: vi.fn(),
  startSearch: vi.fn(),
  deleteRun: vi.fn(),
}));

// EmailDrawer is a complex component; mock it to expose onDecide without modal logic.
vi.mock("./EmailDrawer", () => ({
  EmailDrawer: ({
    lead,
    onDecide,
    onClose,
  }: {
    lead: Lead;
    onDecide: (id: string, action: "approved" | "rejected") => void;
    onClose: () => void;
    runId: string;
  }) => (
    <div role="dialog" aria-label="email drawer">
      <button onClick={() => onDecide(lead.place.id, "approved")}>Approve lead</button>
      <button onClick={onClose}>Close</button>
    </div>
  ),
}));

const { serverApproveLeads } = await import("@/app/actions");
const mockServerApproveLeads = vi.mocked(serverApproveLeads);

// ── Fixtures ──────────────────────────────────────────────────────────────────

function makeLead(id: string, category = "dental"): Lead {
  return {
    place: {
      id,
      name: `Business ${id}`,
      address: "1 Main St, Warsaw",
      lat: 52.0,
      lng: 21.0,
      category,
      rating: 4.5,
      review_count: 50,
      website: "https://example.com",
      phone: "+48 123 456 789",
      hours: [],
      photos: [],
    },
    verdict: { is_qualified: true, score: 0.9, reasoning: "Good fit", icp_fit: {} },
    email: {
      subject: "Hello",
      body: "Let us help you.",
      personalization_hooks: [],
      model_used: "mock",
    },
    decision: "pending",
    decided_at: null,
    error: null,
  };
}

const TWO_LEADS = [makeLead("a"), makeLead("b")];

// ── Tests ──────────────────────────────────────────────────────────────────────

describe("LeadCohortTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    URL.createObjectURL = vi.fn(() => "blob:mock");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    mockServerApproveLeads.mockResolvedValue({ updated: 1 });
  });

  it("'Approve all' increments the approved counter for all leads in that cohort", async () => {
    render(<LeadCohortTable leads={TWO_LEADS} runId="run-1" />);

    expect(screen.getByText("0 / 2 approved")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: /approve all/i }));

    await waitFor(() => {
      expect(screen.getByText("2 / 2 approved")).toBeInTheDocument();
    });

    expect(mockServerApproveLeads).toHaveBeenCalledWith(
      "run-1",
      ["a", "b"],
      "approved",
      undefined,
    );
  });

  it("approving a single lead via the drawer increments the counter by 1", async () => {
    render(<LeadCohortTable leads={TWO_LEADS} runId="run-1" />);

    expect(screen.getByText("0 / 2 approved")).toBeInTheDocument();

    // Expand the cohort card to reveal lead rows.
    await userEvent.click(screen.getByRole("button", { name: /high fit|mid fit|low fit/i }));

    // Click the first lead row to open the drawer.
    await userEvent.click(screen.getByText("Business a"));

    // Mock drawer — click approve.
    const drawer = screen.getByRole("dialog", { name: /email drawer/i });
    await userEvent.click(within(drawer).getByRole("button", { name: /approve lead/i }));

    await waitFor(() => {
      expect(screen.getByText("1 / 2 approved")).toBeInTheDocument();
    });
  });

  it("Export CSV button enables once at least one lead is approved", async () => {
    render(<LeadCohortTable leads={TWO_LEADS} runId="run-1" />);

    expect(screen.getByRole("button", { name: /export csv/i })).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /approve all/i }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /export csv/i })).not.toBeDisabled();
    });
  });

  it("category filter chips render as individual buttons, not a comma blob", () => {
    const leads = [
      makeLead("x", "Advertising Agency, Branding Agency, B2B Service"),
      makeLead("y", "Dental"),
    ];
    render(<LeadCohortTable leads={leads} runId="run-2" />);

    // Each category becomes one pill; multi-value SerpAPI string uses first segment only.
    // "Advertising Agency, Branding Agency, B2B Service" → "Advertising Agency" pill.
    expect(screen.getByRole("button", { name: "Advertising Agency" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Dental" })).toBeInTheDocument();
    // The full comma-blob must NOT appear as a single button.
    expect(
      screen.queryByRole("button", { name: /Advertising Agency, Branding/i }),
    ).toBeNull();
  });
});
