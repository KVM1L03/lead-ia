"use client";

import { useRef, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { deleteRun } from "@/app/actions";
import { approvalRate, formatRelativeTime, statusConfig } from "@/lib/runHistory";

export type RunRowData = {
  id: string;
  prompt: string;
  status: string;
  createdAt: Date;
  emailsGenerated: number;
  approvedCount: number;
};

type Props = { run: RunRowData };

export function RunRow({ run }: Props) {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [isPending, startTransition] = useTransition();
  const [menuOpen, setMenuOpen] = useState(false);

  const cfg = statusConfig(run.status);
  const rate = approvalRate(run.approvedCount, run.emailsGenerated);
  const rateLabel = rate === null ? "—" : `${Math.round(rate * 100)}%`;
  const relDate = formatRelativeTime(new Date(run.createdAt));

  function navigate() {
    router.push(`/runs/${run.id}`);
  }

  function openMenu(e: React.MouseEvent) {
    e.stopPropagation();
    setMenuOpen((v) => !v);
  }

  function openDialog(e: React.MouseEvent) {
    e.stopPropagation();
    setMenuOpen(false);
    dialogRef.current?.showModal();
  }

  function confirmDelete() {
    dialogRef.current?.close();
    startTransition(async () => {
      await deleteRun(run.id);
    });
  }

  return (
    <>
      <tr
        onClick={navigate}
        className="group cursor-pointer border-b border-edge last:border-0 hover:bg-brand-soft/30 transition-colors"
      >
        {/* Prompt */}
        <td className="px-5 py-3 max-w-[280px]">
          <p className="truncate font-sans text-[13px] font-medium text-fg">
            {run.prompt}
          </p>
        </td>

        {/* Date */}
        <td className="px-5 py-3 whitespace-nowrap">
          <span className="font-mono text-[11px] text-muted-fg">{relDate}</span>
        </td>

        {/* Lead count */}
        <td className="px-5 py-3 text-right">
          <span className="font-mono text-[12px] text-fg tabular-nums">
            {run.emailsGenerated > 0 ? run.emailsGenerated : "—"}
          </span>
        </td>

        {/* Approval rate */}
        <td className="px-5 py-3 text-right">
          <span className="font-mono text-[12px] text-fg tabular-nums">{rateLabel}</span>
        </td>

        {/* Status */}
        <td className="px-5 py-3">
          <span
            className={[
              "inline-flex items-center rounded-[3px] border px-2 py-0.5 font-mono text-[10px]",
              cfg.className,
            ].join(" ")}
          >
            {cfg.label}
          </span>
        </td>

        {/* Actions */}
        <td className="px-4 py-3 text-right relative" onClick={(e) => e.stopPropagation()}>
          <button
            onClick={openMenu}
            disabled={isPending}
            aria-label="Run actions"
            className="rounded p-1 text-muted-fg opacity-0 group-hover:opacity-100 hover:text-fg transition-opacity disabled:opacity-30"
          >
            <svg viewBox="0 0 16 16" className="h-4 w-4 fill-current">
              <circle cx="8" cy="3" r="1.2" />
              <circle cx="8" cy="8" r="1.2" />
              <circle cx="8" cy="13" r="1.2" />
            </svg>
          </button>

          {menuOpen && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setMenuOpen(false)}
              />
              <div className="absolute right-4 top-full z-20 mt-1 min-w-[140px] rounded-[3px] border border-edge bg-surface shadow-lg py-1">
                <button
                  onClick={openDialog}
                  className="flex w-full items-center gap-2 px-3 py-2 font-sans text-[12px] text-red-600 hover:bg-red-50"
                >
                  Discard run
                </button>
              </div>
            </>
          )}
        </td>
      </tr>

      {/* Confirmation dialog */}
      <dialog
        ref={dialogRef}
        onClick={(e) => { if (e.target === dialogRef.current) dialogRef.current?.close(); }}
        className="rounded-[3px] border border-edge bg-surface p-0 shadow-xl backdrop:bg-black/30 w-[360px] open:flex open:flex-col"
      >
        <div className="px-6 pt-6 pb-4">
          <p className="font-sans text-[15px] font-semibold text-fg mb-2">
            Discard this run?
          </p>
          <p className="font-sans text-[13px] text-muted-fg leading-relaxed">
            This will permanently delete the run and all associated leads. This
            action cannot be undone.
          </p>
        </div>
        <div className="flex justify-end gap-2 border-t border-edge px-6 py-4">
          <button
            onClick={() => dialogRef.current?.close()}
            className="rounded-[3px] border border-edge px-4 py-1.5 font-sans text-[12px] text-fg hover:bg-skeleton"
          >
            Cancel
          </button>
          <button
            onClick={confirmDelete}
            className="rounded-[3px] bg-red-600 px-4 py-1.5 font-sans text-[12px] font-medium text-white hover:bg-red-700"
          >
            Delete
          </button>
        </div>
      </dialog>
    </>
  );
}
