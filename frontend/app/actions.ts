"use server";

import { searchLeads } from "@/lib/api";

export type StartSearchResult =
  | { status: "success"; runId: string; workflowId: string }
  | { status: "error"; message: string };

export async function startSearch(
  prompt: string,
  limit: number,
  senderContext: string,
): Promise<StartSearchResult> {
  try {
    const response = await searchLeads(prompt, limit, senderContext);
    return {
      status: "success",
      runId: response.run_id,
      workflowId: response.workflow_id,
    };
  } catch (err) {
    return {
      status: "error",
      message: err instanceof Error ? err.message : "Search failed. Try again.",
    };
  }
}
