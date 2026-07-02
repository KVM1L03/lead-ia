"use client";

import { startTransition, useOptimistic, useState } from "react";
import type { Lead } from "@/lib/api";
import { allIndustries, groupIntoCohorts, DEFAULT_FILTERS, type Cohort, type FilterState } from "@/lib/cohorts";
import { serverApproveLeads } from "@/app/actions";
import { EmailDrawer } from "./EmailDrawer";
import { cn } from "@/lib/utils";

type Props = { leads: Lead[]; runId: string };

const BUCKET_COLORS: Record<string, string> = {
  high: "text-emerald-700 bg-emerald-50 border-emerald-200",
  mid: "text-amber-700 bg-amber-50 border-amber-200",
  low: "text-slate-600 bg-slate-50 border-slate-200",
};

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const col = pct > 80 ? "text-emerald-700" : pct >= 50 ? "text-amber-700" : "text-slate-500";
  return <span className={cn("font-mono text-[11px] tabular-nums", col)}>{pct}%</span>;
}

function FiltersBar({
  filters,
  onChange,
  industries,
}: {
  filters: FilterState;
  onChange: (f: FilterState) => void;
  industries: string[];
}) {
  return (
    <div className="mb-5 flex flex-wrap items-center gap-4 rounded-[3px] border border-edge bg-surface px-4 py-2.5">
      <div className="flex items-center gap-2">
        <span className="font-mono text-[9.5px] uppercase tracking-[.18em] text-muted-fg">Score</span>
        <input
          type="range" min={0} max={1} step={0.05}
          value={filters.minScore}
          onChange={(e) => onChange({ ...filters, minScore: parseFloat(e.target.value) })}
          className="w-20 accent-brand"
        />
        <span className="font-mono text-[11px] text-muted-fg tabular-nums">{Math.round(filters.minScore * 100)}%</span>
        <span className="font-mono text-[9.5px] text-muted-fg">–</span>
        <input
          type="range" min={0} max={1} step={0.05}
          value={filters.maxScore}
          onChange={(e) => onChange({ ...filters, maxScore: parseFloat(e.target.value) })}
          className="w-20 accent-brand"
        />
        <span className="font-mono text-[11px] text-muted-fg tabular-nums">{Math.round(filters.maxScore * 100)}%</span>
      </div>
      <label className="flex cursor-pointer items-center gap-1.5">
        <input
          type="checkbox"
          checked={filters.hasWebsite === true}
          onChange={(e) => onChange({ ...filters, hasWebsite: e.target.checked ? true : null })}
          className="accent-brand"
        />
        <span className="font-sans text-[12px] text-fg">Has website</span>
      </label>
      {industries.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {industries.map((ind) => {
            const active = filters.industries.includes(ind);
            return (
              <button
                key={ind}
                onClick={() => {
                  const next = active
                    ? filters.industries.filter((i) => i !== ind)
                    : [...filters.industries, ind];
                  onChange({ ...filters, industries: next });
                }}
                className={cn(
                  "rounded-[3px] border px-2 py-0.5 font-sans text-[11px] transition-colors",
                  active
                    ? "border-brand bg-brand-soft text-brand"
                    : "border-edge bg-white text-muted-fg hover:text-fg",
                )}
              >
                {ind}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

function CohortCard({
  cohort,
  onSelectLead,
  onApproveCohort,
}: {
  cohort: Cohort;
  onSelectLead: (l: Lead) => void;
  onApproveCohort: (placeIds: string[]) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const placeIds = cohort.leads.map((l) => l.place.id);
  const allApproved = cohort.leads.every((l) => l.decision === "approved");

  return (
    <div className="rounded-[3px] border border-edge">
      <div className="flex items-center justify-between gap-4 px-4 py-3">
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex min-w-0 flex-1 items-center gap-3 text-left"
        >
          <svg
            viewBox="0 0 12 12"
            className={cn("h-3 w-3 shrink-0 fill-none stroke-current stroke-2 text-muted-fg transition-transform", expanded && "rotate-90")}
          >
            <path d="M3 2l5 4-5 4" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="truncate font-sans text-[13px] font-medium text-fg">{cohort.label}</span>
          <span className={cn("shrink-0 rounded-[3px] border px-1.5 py-0.5 font-mono text-[10px]", BUCKET_COLORS[cohort.bucket])}>
            avg {Math.round(cohort.stats.avgScore * 100)}%
          </span>
        </button>
        <button
          onClick={() => onApproveCohort(placeIds)}
          disabled={allApproved}
          className="shrink-0 rounded-[3px] bg-brand px-3 py-1.5 font-sans text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-40"
        >
          {allApproved ? "Approved" : "Approve all"}
        </button>
      </div>

      {expanded && (
        <table className="w-full border-t border-edge">
          <thead>
            <tr className="border-b border-edge bg-surface">
              <th className="px-4 py-1.5 text-left font-mono text-[9.5px] uppercase tracking-[.12em] text-muted-fg">Name</th>
              <th className="hidden px-4 py-1.5 text-left font-mono text-[9.5px] uppercase tracking-[.12em] text-muted-fg md:table-cell">Subject</th>
              <th className="px-4 py-1.5 text-right font-mono text-[9.5px] uppercase tracking-[.12em] text-muted-fg">Score</th>
              <th className="px-4 py-1.5 text-right font-mono text-[9.5px] uppercase tracking-[.12em] text-muted-fg">Status</th>
            </tr>
          </thead>
          <tbody>
            {cohort.leads.map((lead) => (
              <tr
                key={lead.place.id}
                onClick={() => onSelectLead(lead)}
                className="cursor-pointer border-b border-edge last:border-0 hover:bg-brand-soft/40"
              >
                <td className="px-4 py-2">
                  <p className="font-sans text-[12px] font-medium text-fg">{lead.place.name}</p>
                  <p className="font-mono text-[10px] text-muted-fg">{lead.place.address.split(",")[0]}</p>
                </td>
                <td className="hidden px-4 py-2 md:table-cell">
                  <p className="max-w-[260px] truncate font-sans text-[12px] text-muted-fg">{lead.email?.subject ?? "—"}</p>
                </td>
                <td className="px-4 py-2 text-right">
                  <ScoreBadge score={lead.verdict?.score ?? 0} />
                </td>
                <td className="px-4 py-2 text-right">
                  <span className={cn(
                    "font-mono text-[10px]",
                    lead.decision === "approved" ? "text-emerald-700" : lead.decision === "rejected" ? "text-red-600" : "text-muted-fg",
                  )}>
                    {lead.decision}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export function LeadCohortTable({ leads: initialLeads, runId }: Props) {
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const [optimisticLeads, applyOptimistic] = useOptimistic(
    initialLeads,
    (state, { placeIds, action }: { placeIds: string[]; action: "approved" | "rejected" }) =>
      state.map((l) => placeIds.includes(l.place.id) ? { ...l, decision: action as Lead["decision"] } : l),
  );

  const cohorts = groupIntoCohorts(optimisticLeads, filters);
  const industries = allIndustries(optimisticLeads);

  function showToast(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 3000);
  }

  async function handleApprove(placeIds: string[], action: "approved" | "rejected", editedEmails?: Record<string, { subject: string; body: string }>) {
    startTransition(async () => {
      applyOptimistic({ placeIds, action });
      try {
        await serverApproveLeads(runId, placeIds, action, editedEmails);
      } catch {
        showToast("Failed to save decision — please try again.");
      }
    });
  }

  function handleDecide(placeId: string, action: "approved" | "rejected", edit?: { subject: string; body: string }) {
    const editedEmails = edit ? { [placeId]: edit } : undefined;
    void handleApprove([placeId], action, editedEmails);
    setSelectedLead(null);
  }

  const totalQualified = optimisticLeads.filter((l) => l.verdict?.is_qualified).length;
  const totalApproved = optimisticLeads.filter((l) => l.decision === "approved").length;

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="mb-6 flex items-baseline justify-between">
        <div>
          <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[.18em] text-muted-fg">Review</p>
          <h1 className="font-serif text-[22px] leading-snug tracking-[-0.01em] text-fg">
            {totalApproved} / {totalQualified} approved
          </h1>
        </div>
      </div>

      <FiltersBar filters={filters} onChange={setFilters} industries={industries} />

      {cohorts.length === 0 ? (
        <div className="rounded-[3px] border border-edge px-6 py-8 text-center font-sans text-[13px] text-muted-fg">
          No leads match the current filters.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {cohorts.map((cohort) => (
            <CohortCard
              key={`${cohort.bucket}::${cohort.industry}`}
              cohort={cohort}
              onSelectLead={setSelectedLead}
              onApproveCohort={(ids) => void handleApprove(ids, "approved")}
            />
          ))}
        </div>
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-[3px] border border-edge bg-surface px-4 py-2 font-sans text-[12px] text-fg shadow-lg">
          {toast}
        </div>
      )}

      {selectedLead && (
        <EmailDrawer
          key={selectedLead.place.id}
          lead={selectedLead}
          runId={runId}
          onClose={() => setSelectedLead(null)}
          onDecide={handleDecide}
        />
      )}
    </div>
  );
}
