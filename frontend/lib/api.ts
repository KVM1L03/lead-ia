// Typed fetch wrappers for the LeadForge backend API.
// All functions are async and throw on non-2xx responses.

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── Backend response types (mirror shared/schemas.py) ─────────────────────────

export type PlaceDetails = {
  id: string;
  name: string;
  address: string;
  lat: number;
  lng: number;
  category: string;
  rating: number;
  review_count: number;
  website: string | null;
  phone: string | null;
  hours: string[];
  photos: string[];
};

export type QualifierVerdict = {
  is_qualified: boolean;
  score: number;
  reasoning: string;
  icp_fit: Record<string, boolean>;
};

export type GeneratedEmail = {
  subject: string;
  body: string;
  personalization_hooks: string[];
  model_used: string;
};

export type Lead = {
  place: PlaceDetails;
  verdict: QualifierVerdict | null;
  email: GeneratedEmail | null;
  decision: "pending" | "approved" | "rejected";
  decided_at: string | null;
  error: string | null;
};

export type ProgressCounts = {
  scraped: number;
  qualified: number;
  emails_generated: number;
};

export type SearchResponse = {
  workflow_id: string;
  run_id: string;
};

export type StatusResponse = {
  status: "scraping" | "qualifying" | "generating" | "completed" | "failed";
  progress: ProgressCounts;
  results: Lead[];
};

export type EditedEmail = {
  subject: string;
  body: string;
};

export type ApproveResponse = {
  updated: number;
};

// ── Helpers ───────────────────────────────────────────────────────────────────

async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} ${path}: ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Public API ────────────────────────────────────────────────────────────────

export async function searchLeads(
  prompt: string,
  limit: number,
  senderContext: string,
): Promise<SearchResponse> {
  return apiFetch<SearchResponse>("/api/leads/search", {
    method: "POST",
    body: JSON.stringify({
      prompt,
      limit,
      sender_context: senderContext,
    }),
  });
}

export async function getStatus(workflowId: string): Promise<StatusResponse> {
  const res = await fetch(`/api/leads/status/${encodeURIComponent(workflowId)}`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText);
    throw new Error(`${res.status} /api/leads/status: ${text}`);
  }
  return res.json() as Promise<StatusResponse>;
}

export async function approveLeads(
  runId: string,
  leadIds: string[],
  action: "approved" | "rejected",
  editedEmails?: Record<string, EditedEmail>,
): Promise<ApproveResponse> {
  return apiFetch<ApproveResponse>("/api/leads/approve", {
    method: "POST",
    body: JSON.stringify({
      run_id: runId,
      lead_ids: leadIds,
      action,
      ...(editedEmails ? { edited_emails: editedEmails } : {}),
    }),
  });
}
