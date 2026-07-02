import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { RunRow } from "@/components/RunRow";

export default async function HistoryPage() {
  const runs = await prisma.run.findMany({
    take: 50,
    orderBy: { createdAt: "desc" },
    select: {
      id: true,
      prompt: true,
      status: true,
      createdAt: true,
      emails_generated: true,
      leads: {
        where: { decision: "approved" },
        select: { id: true },
      },
    },
  });

  return (
    <section className="px-8 py-10">
      <div className="mb-8 flex items-end justify-between">
        <div>
          <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[.18em] text-muted-fg">
            History
          </p>
          <h1 className="font-serif text-[28px] leading-[1.35] tracking-[-0.015em] text-fg">
            Past runs
          </h1>
        </div>
        <Link
          href="/search"
          className="inline-flex items-center gap-2 rounded-[3px] bg-brand px-4 py-2 font-sans text-[13px] font-medium text-white hover:brightness-90 transition-[filter]"
        >
          New search
        </Link>
      </div>

      {runs.length === 0 ? (
        <div className="rounded-[3px] border border-edge bg-surface px-6 py-10 text-center">
          <p className="font-sans text-[13px] text-muted-fg">
            No runs yet.{" "}
            <Link href="/search" className="text-brand hover:underline">
              Start a search
            </Link>{" "}
            to generate your first cohort.
          </p>
        </div>
      ) : (
        <div className="rounded-[3px] border border-edge overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-edge bg-surface">
                <th className="px-5 py-2.5 text-left font-mono text-[9.5px] uppercase tracking-[.14em] text-muted-fg">
                  Prompt
                </th>
                <th className="px-5 py-2.5 text-left font-mono text-[9.5px] uppercase tracking-[.14em] text-muted-fg">
                  Date
                </th>
                <th className="px-5 py-2.5 text-right font-mono text-[9.5px] uppercase tracking-[.14em] text-muted-fg">
                  Leads
                </th>
                <th className="px-5 py-2.5 text-right font-mono text-[9.5px] uppercase tracking-[.14em] text-muted-fg">
                  Approved
                </th>
                <th className="px-5 py-2.5 text-left font-mono text-[9.5px] uppercase tracking-[.14em] text-muted-fg">
                  Status
                </th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <RunRow
                  key={run.id}
                  run={{
                    id: run.id,
                    prompt: run.prompt,
                    status: run.status,
                    createdAt: run.createdAt,
                    emailsGenerated: run.emails_generated,
                    approvedCount: run.leads.length,
                  }}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
