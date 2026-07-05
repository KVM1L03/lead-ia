"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getStatus } from "@/lib/api";
import type { StatusResponse } from "@/lib/api";
import { PipelineStageRow } from "@/components/PipelineStageRows";
import {
  computeStages,
  synthesizeEvents,
  TERMINAL_STATUSES,
  type ProgressSnapshot,
} from "@/lib/runProgress";
import { cn } from "@/lib/utils";

const POLL_INTERVAL_MS = 2000;
const MAX_EVENTS = 5;

type InitialRun = {
  status: string;
  scraped: number;
  qualified: number;
  emails_generated: number;
  limit: number;
  prompt: string;
};

type Props = {
  runId: string;
  initialRun: InitialRun;
};

function toSnapshot(
  s: StatusResponse | InitialRun,
  isInitial?: boolean,
): ProgressSnapshot {
  if (isInitial) {
    const r = s as InitialRun;
    return {
      status: r.status,
      scraped: r.scraped,
      qualified: r.qualified,
      emails_generated: r.emails_generated,
    };
  }
  const r = s as StatusResponse;
  return {
    status: r.status,
    scraped: r.progress.scraped,
    qualified: r.progress.qualified,
    emails_generated: r.progress.emails_generated,
  };
}

// ── Main component ─────────────────────────────────────────────────────────────

export function RunProgressView({ runId, initialRun }: Props) {
  const router = useRouter();
  const [snapshot, setSnapshot] = useState<ProgressSnapshot>(() =>
    toSnapshot(initialRun, true),
  );
  const [limit] = useState(initialRun.limit);
  const [events, setEvents] = useState<string[]>([]);
  const [pollError, setPollError] = useState(false);
  const prevRef = useRef<ProgressSnapshot>(toSnapshot(initialRun, true));

  const pushEvents = useCallback((newEvents: string[]) => {
    if (newEvents.length === 0) return;
    setEvents((prev) => [...prev, ...newEvents].slice(-MAX_EVENTS));
  }, []);

  useEffect(() => {
    if (TERMINAL_STATUSES.has(snapshot.status)) return;

    const controller = new AbortController();
    let timerId: ReturnType<typeof setTimeout>;

    async function poll() {
      try {
        const data = await getStatus(runId);
        const next: ProgressSnapshot = {
          status: data.status,
          scraped: data.progress.scraped,
          qualified: data.progress.qualified,
          emails_generated: data.progress.emails_generated,
        };
        const evs = synthesizeEvents(prevRef.current, next);
        prevRef.current = next;
        setSnapshot(next);
        setPollError(false);
        pushEvents(evs);
        if (next.status === "completed") router.refresh();
      } catch {
        if (!controller.signal.aborted) setPollError(true);
      }

      if (!controller.signal.aborted && !TERMINAL_STATUSES.has(prevRef.current.status)) {
        timerId = setTimeout(poll, POLL_INTERVAL_MS);
      }
    }

    timerId = setTimeout(poll, POLL_INTERVAL_MS);
    return () => {
      controller.abort();
      clearTimeout(timerId);
    };
  }, [runId, snapshot.status, pushEvents, router]);

  const stages = computeStages(snapshot.status, snapshot, limit);
  const isComplete = snapshot.status === "completed";
  const isFailed = snapshot.status === "failed";

  return (
    <div className="mx-auto max-w-xl px-8 py-10">
      {/* Header */}
      <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[.18em] text-muted-fg">
        Run
      </p>
      <h1 className="mb-8 font-serif text-[22px] leading-snug tracking-[-0.01em] text-fg line-clamp-2">
        {initialRun.prompt}
      </h1>

      {/* Poll error warning */}
      {pollError && (
        <div className="mb-6 rounded-[3px] border border-edge bg-surface px-4 py-2.5 font-mono text-[11px] text-muted-fg">
          Connection interrupted — retrying…
        </div>
      )}

      {/* Pipeline stages */}
      <div className="mb-8 flex flex-col gap-6">
        {stages.map((stage, i) => (
          <PipelineStageRow key={stage.label} stage={stage} index={i} />
        ))}
      </div>

      {/* Live tail */}
      {events.length > 0 && (
        <div className="mb-8 rounded-[3px] border border-edge bg-surface p-4">
          <p className="mb-2 font-mono text-[9.5px] uppercase tracking-[.18em] text-muted-fg">
            Activity
          </p>
          <ul className="space-y-1">
            {events.map((ev, i) => (
              <li
                key={i}
                className={cn(
                  "font-mono text-[11px] leading-relaxed",
                  i === events.length - 1 ? "text-fg" : "text-muted-fg",
                )}
              >
                {ev}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Terminal states */}
      {isComplete && (
        <div className="rounded-[3px] border border-brand/30 bg-brand-soft px-5 py-4">
          <p className="font-sans text-[13px] font-medium text-fg">
            Done —{" "}
            <span className="text-brand">{snapshot.emails_generated}</span>{" "}
            {snapshot.emails_generated === 1 ? "lead" : "leads"} ready for review
          </p>
        </div>
      )}
      {isFailed && (
        <div className="rounded-[3px] border border-edge bg-surface px-5 py-4">
          <p className="font-sans text-[13px] font-medium text-fg">
            Run failed — check worker logs
          </p>
        </div>
      )}
    </div>
  );
}
