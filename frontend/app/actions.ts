"use server";

import { revalidatePath } from "next/cache";
import { approveLeads, type EditedEmail } from "@/lib/api";
import { prisma } from "@/lib/prisma";

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
