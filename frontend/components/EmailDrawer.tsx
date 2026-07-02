"use client";

import { useEffect, useState } from "react";
import type { Lead } from "@/lib/api";

type EditedEmail = { subject: string; body: string };

type Props = {
  lead: Lead;
  runId: string;
  onClose: () => void;
  onDecide: (placeId: string, action: "approved" | "rejected", edit?: EditedEmail) => void;
};

function lsKey(runId: string, placeId: string) {
  return `lf:${runId}:${placeId}`;
}

function readDraft(runId: string, placeId: string): EditedEmail | null {
  try {
    const raw = window.localStorage.getItem(lsKey(runId, placeId));
    return raw ? (JSON.parse(raw) as EditedEmail) : null;
  } catch {
    return null;
  }
}

export function EmailDrawer({ lead, runId, onClose, onDecide }: Props) {
  const [subject, setSubject] = useState(() => {
    const draft = typeof window !== "undefined" ? readDraft(runId, lead.place.id) : null;
    return draft?.subject ?? lead.email?.subject ?? "";
  });
  const [body, setBody] = useState(() => {
    const draft = typeof window !== "undefined" ? readDraft(runId, lead.place.id) : null;
    return draft?.body ?? lead.email?.body ?? "";
  });

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const isDirty = subject !== (lead.email?.subject ?? "") || body !== (lead.email?.body ?? "");

  function saveDraft() {
    localStorage.setItem(lsKey(runId, lead.place.id), JSON.stringify({ subject, body }));
  }

  function decide(action: "approved" | "rejected") {
    localStorage.removeItem(lsKey(runId, lead.place.id));
    onDecide(lead.place.id, action, isDirty ? { subject, body } : undefined);
  }

  return (
    <>
      <div
        className="fixed inset-0 z-20 bg-black/20"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className="fixed right-0 top-0 z-30 flex h-full w-[480px] flex-col border-l border-edge bg-surface shadow-xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-edge px-6 py-4">
          <div className="min-w-0">
            <p className="truncate font-sans text-[13px] font-semibold text-fg">
              {lead.place.name}
            </p>
            <p className="truncate font-mono text-[11px] text-muted-fg">
              {lead.place.address}
            </p>
          </div>
          <button
            onClick={onClose}
            className="mt-0.5 shrink-0 rounded p-1 text-muted-fg hover:text-fg"
            aria-label="Close"
          >
            <svg viewBox="0 0 16 16" className="h-4 w-4 fill-none stroke-current stroke-2" strokeLinecap="round">
              <path d="M3 3l10 10M13 3L3 13" />
            </svg>
          </button>
        </div>

        {/* Email edit */}
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-6 py-4">
          <div className="flex flex-col gap-1">
            <label className="font-mono text-[9.5px] uppercase tracking-[.18em] text-muted-fg">
              Subject
            </label>
            <input
              className="rounded-[3px] border border-edge bg-white px-3 py-2 font-sans text-[13px] text-fg outline-none focus:border-brand"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>

          <div className="flex flex-1 flex-col gap-1">
            <label className="font-mono text-[9.5px] uppercase tracking-[.18em] text-muted-fg">
              Body
            </label>
            <textarea
              className="h-full min-h-[240px] flex-1 resize-none rounded-[3px] border border-edge bg-white px-3 py-2 font-sans text-[13px] text-fg outline-none focus:border-brand"
              value={body}
              onChange={(e) => setBody(e.target.value)}
            />
          </div>

          {/* Personalization hooks */}
          {lead.email?.personalization_hooks && lead.email.personalization_hooks.length > 0 && (
            <div className="flex flex-col gap-1.5">
              <p className="font-mono text-[9.5px] uppercase tracking-[.18em] text-muted-fg">
                Hooks used
              </p>
              <div className="flex flex-wrap gap-1.5">
                {lead.email.personalization_hooks.map((h) => (
                  <span
                    key={h}
                    className="rounded-[3px] border border-edge bg-white px-2 py-0.5 font-mono text-[10px] text-muted-fg"
                  >
                    {h}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-center justify-between gap-3 border-t border-edge px-6 py-4">
          <button
            onClick={saveDraft}
            disabled={!isDirty}
            className="rounded-[3px] border border-edge px-3 py-1.5 font-sans text-[12px] text-muted-fg hover:text-fg disabled:opacity-40"
          >
            Save draft
          </button>
          <div className="flex gap-2">
            <button
              onClick={() => decide("rejected")}
              className="rounded-[3px] border border-edge px-4 py-1.5 font-sans text-[12px] text-fg hover:border-fg"
            >
              Reject
            </button>
            <button
              onClick={() => decide("approved")}
              className="rounded-[3px] bg-brand px-4 py-1.5 font-sans text-[12px] font-medium text-white hover:opacity-90"
            >
              Approve
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
