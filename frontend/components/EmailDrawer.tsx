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
        className="fixed inset-0 z-20 bg-black/25 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className="fixed right-3 top-3 bottom-3 z-30 flex w-[420px] flex-col rounded-3xl border border-glass-edge bg-glass backdrop-blur-2xl shadow-[0_8px_32px_rgba(0,0,0,.06)] overflow-hidden">
        {/* Header */}
        <div className="flex items-start justify-between gap-4 border-b border-edge px-6 py-4">
          <div className="min-w-0">
            <p className="truncate font-sans text-[13px] font-semibold text-fg">
              {lead.place.name}
            </p>
            <p className="truncate font-mono text-[11px] text-muted-fg">
              {lead.place.address}
            </p>
            {lead.place.website && (
              <a
                href={lead.place.website}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-block max-w-full truncate font-mono text-[10px] text-brand hover:underline mt-0.5"
              >
                {lead.place.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}
              </a>
            )}
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
              className="rounded-xl border border-edge-input bg-white/70 px-3 py-2 font-sans text-[13px] text-fg outline-none focus:border-brand/50"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
            />
          </div>

          <div className="flex flex-1 flex-col gap-1">
            <label className="font-mono text-[9.5px] uppercase tracking-[.18em] text-muted-fg">
              Body
            </label>
            <textarea
              className="h-full min-h-[240px] flex-1 resize-none rounded-2xl border border-edge-input bg-white/70 px-3 py-2 font-sans text-[13px] text-fg outline-none focus:border-brand/50"
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
                    className="rounded-full border border-edge bg-white/70 px-2.5 py-0.5 font-mono text-[10px] text-muted-fg"
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
            className="rounded-xl border border-edge px-3 py-1.5 font-sans text-[12px] text-muted-fg hover:text-fg disabled:opacity-40"
          >
            Save draft
          </button>
          <div className="flex gap-2">
            <button
              onClick={() => decide("rejected")}
              className="rounded-xl border border-edge px-4 py-1.5 font-sans text-[12px] text-fg hover:border-reject/40 hover:text-reject hover:bg-reject-soft transition-colors"
            >
              Reject
            </button>
            <button
              onClick={() => decide("approved")}
              className="rounded-xl bg-brand px-4 py-1.5 font-sans text-[12px] font-medium text-white shadow-[0_8px_20px_rgba(200,116,46,.32)] hover:scale-[1.02] transition-transform"
            >
              Approve
            </button>
          </div>
        </div>
      </aside>
    </>
  );
}
