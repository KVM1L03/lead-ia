"use server";

import { revalidatePath } from "next/cache";
import { approveLeads, searchLeads, type EditedEmail, type Lead } from "@/lib/api";
import { prisma } from "@/lib/prisma";

export type StartSearchResult =
  | { status: "success"; runId: string; workflowId: string; mode: "temporal" | "sync"; results: Lead[] }
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
      mode: response.mode,
      results: response.results,
    };
  } catch (err) {
    return {
      status: "error",
      message: err instanceof Error ? err.message : "Search failed. Try again.",
    };
  }
}

export async function deleteRun(runId: string): Promise<void> {
  await prisma.run.delete({ where: { id: runId } });
  revalidatePath("/history");
}

export async function serverApproveLeads(
  runId: string,
  placeIds: string[],
  action: "approved" | "rejected",
  editedEmails?: Record<string, EditedEmail>,
): Promise<{ updated: number }> {
  return approveLeads(runId, placeIds, action, editedEmails);
}
