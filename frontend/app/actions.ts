"use server";

import { approveLeads, type EditedEmail } from "@/lib/api";

export async function serverApproveLeads(
  runId: string,
  placeIds: string[],
  action: "approved" | "rejected",
  editedEmails?: Record<string, EditedEmail>,
): Promise<{ updated: number }> {
  return approveLeads(runId, placeIds, action, editedEmails);
}
