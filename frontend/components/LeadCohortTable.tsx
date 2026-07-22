"use client";

import { startTransition, useOptimistic, useState } from "react";
import type { Lead } from "@/lib/api";
import { allIndustries, groupIntoCohorts, DEFAULT_FILTERS, type Cohort, type FilterState } from "@/lib/cohorts";
import { serverApproveLeads, serverExportLeads } from "@/app/actions";
import { EmailDrawer } from "./EmailDrawer";
import { ExportCsvButton } from "./ExportCsvButton";
import { cn } from "@/lib/utils";

type Props = { leads: Lead[]; runId: string };

const BUCKET_COLORS: Record<string, string> = {
  high: "text-success-fg bg-success-soft border-success/30",
  mid: "text-warning-fg bg-warning-soft border-warning/40",
  low: "text-subtle bg-skeleton border-edge",
};

function ScoreBadge({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const col = pct > 80 ? "text-success-fg" : pct >= 50 ? "text-warning-fg" : "text-subtle";
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
    <div className="mb-5 flex flex-wrap items-center gap-4 rounded-2xl border border-glass-edge bg-glass backdrop-blur-md shadow-[0_6px_24px_rgba(0,0,0,.04)] px-4 py-2.5">
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
                  "rounded-full border px-2.5 py-0.5 font-sans text-[11px] transition-colors",
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
    <div className="rounded-2xl border border-glass-edge bg-glass backdrop-blur-md shadow-[0_6px_24px_rgba(0,0,0,.04)] overflow-hidden">
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
          <span className={cn("shrink-0 rounded-full border px-2 py-0.5 font-mono text-[10px]", BUCKET_COLORS[cohort.bucket])}>
            avg {Math.round(cohort.stats.avgScore * 100)}%
          </span>
        </button>
        <button
          onClick={() => onApproveCohort(placeIds)}
          disabled={allApproved}
          className="shrink-0 rounded-xl bg-brand px-3 py-1.5 font-sans text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-40"
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
                    lead.decision === "approved" ? "text-success-fg" : lead.decision === "rejected" ? "text-reject" : "text-muted-fg",
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

  // baseLeads is the committed source of truth. useOptimistic builds on top of it
  // so the optimistic update persists after the transition instead of reverting.
  const [baseLeads, setBaseLeads] = useState<Lead[]>(initialLeads);
  const [optimisticLeads, applyOptimistic] = useOptimistic(
    baseLeads,
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
        // Commit: update the base state so the optimistic change persists.
        // On error (catch), baseLeads is NOT updated → useOptimistic auto-reverts.
        setBaseLeads((prev) =>
          prev.map((l) =>
            placeIds.includes(l.place.id) ? { ...l, decision: action } : l,
          ),
        );
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

  const [isApproveExporting, setIsApproveExporting] = useState(false);

  async function handleApproveAllAndExport(): Promise<void> {
    const qualifiedIds = optimisticLeads
      .filter((l) => l.verdict?.is_qualified)
      .map((l) => l.place.id);
    if (qualifiedIds.length === 0) return;

    setIsApproveExporting(true);
    startTransition(async () => {
      applyOptimistic({ placeIds: qualifiedIds, action: "approved" });
      try {
        await serverApproveLeads(runId, qualifiedIds, "approved");
        const newLeads = baseLeads.map((l) =>
          qualifiedIds.includes(l.place.id) ? { ...l, decision: "approved" as Lead["decision"] } : l,
        );
        setBaseLeads(newLeads);

        const approvedLeads = newLeads.filter((l) => l.decision === "approved");
        const result = await serverExportLeads(runId, approvedLeads);
        if (!result.ok) {
          showToast(result.error);
          return;
        }
        const blob = new Blob([result.csv], { type: "text/csv;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        try {
          const a = document.createElement("a");
          a.href = url;
          a.download = `leadia-export-${new Date().toISOString().slice(0, 10)}.csv`;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
        } finally {
          URL.revokeObjectURL(url);
        }
      } catch {
        showToast("Failed to approve and export — please try again.");
      } finally {
        setIsApproveExporting(false);
      }
    });
  }

  const totalQualified = optimisticLeads.filter((l) => l.verdict?.is_qualified).length;
  const totalApproved = optimisticLeads.filter((l) => l.decision === "approved").length;

  return (
    <div className="mx-auto max-w-3xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[.18em] text-muted-fg">Review</p>
          <h1 className="font-serif text-[22px] leading-snug tracking-[-0.01em] text-fg">
            {totalApproved} / {totalQualified} approved
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void handleApproveAllAndExport()}
            disabled={isApproveExporting || totalQualified === 0}
            title={totalQualified === 0 ? "No qualified leads to export" : "Approve all leads and download CSV"}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5",
              "font-sans text-[12px] font-medium transition-colors",
              "bg-brand text-white hover:opacity-90",
              (isApproveExporting || totalQualified === 0) && "cursor-not-allowed opacity-50",
            )}
          >
            {isApproveExporting ? (
              "Exporting…"
            ) : (
              <>
                <svg viewBox="0 0 12 12" aria-hidden="true" className="h-3 w-3 shrink-0 fill-none stroke-current stroke-[1.5]">
                  <path d="M6 1v7M3 5l3 3 3-3M1 10h10" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Approve all & export
              </>
            )}
          </button>
          <ExportCsvButton
            runId={runId}
            approvedLeads={optimisticLeads.filter((l) => l.decision === "approved")}
            onError={showToast}
          />
        </div>
      </div>

      <FiltersBar filters={filters} onChange={setFilters} industries={industries} />

      {cohorts.length === 0 ? (
        <div className="rounded-2xl border border-glass-edge bg-glass backdrop-blur-md px-6 py-8 text-center font-sans text-[13px] text-muted-fg">
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
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 rounded-xl border border-glass-edge bg-glass backdrop-blur-md px-4 py-2 font-sans text-[12px] text-fg shadow-lg">
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
