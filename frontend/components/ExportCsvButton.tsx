"use client";

import { useState } from "react";
import { serverExportLeads } from "@/app/actions";
import type { Lead } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  runId: string;
  approvedLeads: Lead[];
  onError: (msg: string) => void;
}

export function ExportCsvButton({ runId, approvedLeads, onError }: Props) {
  const [isExporting, setIsExporting] = useState(false);

  const hasApproved = approvedLeads.length > 0;
  const disabled = !hasApproved || isExporting;

  async function handleExport(): Promise<void> {
    setIsExporting(true);
    try {
      const result = await serverExportLeads(runId, approvedLeads);
      if (!result.ok) {
        onError(result.error);
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
      onError("Export failed — please try again.");
    } finally {
      setIsExporting(false);
    }
  }

  return (
    <button
      type="button"
      onClick={() => void handleExport()}
      disabled={disabled}
      title={hasApproved ? undefined : "Approve at least one lead to export"}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-[3px] border border-edge px-3 py-1.5",
        "font-sans text-[12px] font-medium transition-colors",
        hasApproved && !isExporting
          ? "text-fg hover:bg-surface"
          : "cursor-not-allowed text-muted-fg opacity-50",
      )}
    >
      {isExporting ? (
        "Exporting…"
      ) : (
        <>
          <svg
            viewBox="0 0 12 12"
            aria-hidden="true"
            className="h-3 w-3 shrink-0 fill-none stroke-current stroke-[1.5]"
          >
            <path
              d="M6 1v7M3 5l3 3 3-3M1 10h10"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          Export CSV
        </>
      )}
    </button>
  );
}
