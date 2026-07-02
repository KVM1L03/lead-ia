"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getStatus } from "@/lib/api";
import type { StatusResponse } from "@/lib/api";
import {
  computeStages,
  synthesizeEvents,
  TERMINAL_STATUSES,
  type ProgressSnapshot,
  type StageState,
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

// ── Sub-components ─────────────────────────────────────────────────────────────

function StageIndicator({
  state,
  index,
}: {
  state: StageState;
  index: number;
}) {
  return (
    <div
      className={cn(
        "relative flex h-8 w-8 flex-none items-center justify-center rounded-full border-2 text-[11px] font-mono font-medium transition-colors duration-300",
        state === "done" && "border-brand bg-brand text-white",
        state === "active" && "border-brand bg-brand-soft text-brand",
        state === "pending" && "border-edge bg-surface text-muted-fg",
      )}
    >
      {state === "done" ? (
        <svg viewBox="0 0 12 12" className="h-3 w-3 fill-current">
          <path d="M1.5 6.5 4.5 9.5 10.5 3" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : (
        index + 1
      )}
      {state === "active" && (
        <span className="absolute inset-0 rounded-full border-2 border-brand animate-ping opacity-40" />
      )}
    </div>
  );
}

function ProgressBar({
  current,
  total,
  state,
}: {
  current: number;
  total: number;
  state: StageState;
}) {
  const pct = total > 0 ? Math.min(100, Math.round((current / total) * 100)) : 0;
  return (
    <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-edge">
      <div
        className={cn(
          "h-full rounded-full transition-all duration-500",
          state === "done" && "bg-brand",
          state === "active" && "bg-brand",
          state === "pending" && "bg-muted-fg/30",
        )}
        style={{ width: `${state === "pending" ? 0 : pct}%` }}
      />
    </div>
  );
}

function StageRow({
  stage,
  index,
}: {
  stage: ReturnType<typeof computeStages>[number];
  index: number;
}) {
  const pctLabel =
    stage.total > 0
      ? `${stage.current} / ${stage.total}`
      : stage.current.toString();

  return (
    <div className="flex items-start gap-4">
      <StageIndicator state={stage.state} index={index} />
      <div className="min-w-0 flex-1 pt-1">
        <div className="flex items-baseline justify-between gap-2">
          <span
            className={cn(
              "text-[13px] font-sans font-medium leading-none",
              stage.state === "pending" ? "text-muted-fg" : "text-fg",
            )}
          >
            {stage.label}
          </span>
          {stage.state !== "pending" && (
            <span className="font-mono text-[11px] text-muted-fg tabular-nums">
              {pctLabel}
            </span>
          )}
        </div>
        <ProgressBar current={stage.current} total={stage.total} state={stage.state} />
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────────

export function RunProgressView({ runId, initialRun }: Props) {
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
  }, [runId, snapshot.status, pushEvents]);

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
          <StageRow key={stage.label} stage={stage} index={i} />
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
