import { notFound } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { RunProgressView } from "@/components/RunProgressView";
import { LeadCohortTable } from "@/components/LeadCohortTable";
import type { Lead } from "@/lib/api";

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const run = await prisma.run.findUnique({ where: { id } });
  if (!run) notFound();

  const leads: Lead[] = run.leads_json ? (JSON.parse(run.leads_json) as Lead[]) : [];
  const showCohorts = run.status === "completed" && leads.length > 0;

  if (showCohorts) {
    return <LeadCohortTable leads={leads} runId={id} />;
  }

  return (
    <RunProgressView
      runId={id}
      initialRun={{
        status: run.status,
        scraped: run.scraped,
        qualified: run.qualified,
        emails_generated: run.emails_generated,
        limit: run.limit,
        prompt: run.prompt,
      }}
    />
  );
}
