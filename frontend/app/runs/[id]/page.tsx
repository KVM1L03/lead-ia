import { notFound } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { RunProgressView } from "@/components/RunProgressView";

export default async function RunPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const run = await prisma.run.findUnique({ where: { id } });
  if (!run) notFound();

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
