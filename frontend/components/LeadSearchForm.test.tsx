import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Toast } from "@base-ui/react/toast";
import { LeadSearchForm } from "./LeadSearchForm";
import type { StartSearchResult } from "@/app/actions";

// ── Mocks ─────────────────────────────────────────────────────────────────────

// vi.mock is hoisted — the factory runs before any import, so the "use server"
// directive in the real module never executes during tests.
vi.mock("@/app/actions", () => ({
  startSearch: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// Import the mocked module AFTER vi.mock declaration so we get the mock instance.
const { startSearch } = await import("@/app/actions");
const mockStartSearch = vi.mocked(startSearch);

// ── Helpers ───────────────────────────────────────────────────────────────────

function Wrapper({ children }: { children: React.ReactNode }) {
  return <Toast.Provider>{children}</Toast.Provider>;
}

function renderForm() {
  return render(<LeadSearchForm />, { wrapper: Wrapper });
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("LeadSearchForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it("renders with default values", () => {
    renderForm();

    expect(
      screen.getByRole("textbox", { name: /describe the leads/i }),
    ).toHaveValue("");

    expect(
      screen.getByRole("textbox", { name: /who you are/i }),
    ).toHaveValue("");

    expect(screen.getByRole("slider", { name: /result count/i })).toHaveValue(
      "50",
    );

    expect(
      screen.getByRole("button", { name: /start search/i }),
    ).not.toBeDisabled();
  });

  it("calls startSearch with correct args on submit", async () => {
    mockStartSearch.mockResolvedValueOnce({
      status: "success",
      runId: "run-abc",
      workflowId: "wf-abc",
    } satisfies StartSearchResult);

    renderForm();

    await userEvent.type(
      screen.getByRole("textbox", { name: /describe the leads/i }),
      "dental clinics in Warsaw",
    );

    await userEvent.type(
      screen.getByRole("textbox", { name: /who you are/i }),
      "I sell dental SaaS",
    );

    await userEvent.click(screen.getByRole("button", { name: /start search/i }));

    await waitFor(() => {
      expect(mockStartSearch).toHaveBeenCalledWith(
        "dental clinics in Warsaw",
        50,
        "I sell dental SaaS",
      );
    });
  });

  it("hides the submit button while submission is pending", async () => {
    let resolve!: (v: StartSearchResult) => void;
    mockStartSearch.mockReturnValueOnce(
      new Promise<StartSearchResult>((r) => {
        resolve = r;
      }),
    );

    renderForm();

    await userEvent.type(
      screen.getByRole("textbox", { name: /describe the leads/i }),
      "dental clinics in Warsaw",
    );

    await userEvent.click(screen.getByRole("button", { name: /start search/i }));

    // Submit button is replaced by the inline skeleton while pending
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: /start search/i }),
      ).not.toBeInTheDocument();
    });

    // Resolve so React can clean up async state
    await act(async () => {
      resolve({ status: "success", runId: "r", workflowId: "w" });
    });
  });
});
