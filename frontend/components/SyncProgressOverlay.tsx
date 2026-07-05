"use client";

import { useEffect, useRef, useState } from "react";
import { PipelineStageList } from "@/components/PipelineStageRows";
import {
  synthesizeEvents,
  type ProgressSnapshot,
} from "@/lib/runProgress";
import { computeSimulatedSnapshot } from "@/lib/simulatedProgress";

const TICK_MS = 400;
const MAX_EVENTS = 5;

type Props = {
  prompt: string;
  limit: number;
};

export function SyncProgressOverlay({ prompt, limit }: Props) {
  const [snapshot, setSnapshot] = useState<ProgressSnapshot>(() =>
    computeSimulatedSnapshot(0, limit),
  );
  const [events, setEvents] = useState<string[]>(["Starting pipeline…"]);
  const prevRef = useRef<ProgressSnapshot>(snapshot);
  const startRef = useRef(0);

  useEffect(() => {
    startRef.current = Date.now();
    prevRef.current = computeSimulatedSnapshot(0, limit);
    setSnapshot(prevRef.current);
    setEvents(["Starting pipeline…"]);

    const id = setInterval(() => {
      const elapsed = Date.now() - startRef.current;
      const next = computeSimulatedSnapshot(elapsed, limit);
      const newEvents = synthesizeEvents(prevRef.current, next);
      prevRef.current = next;
      setSnapshot(next);
      if (newEvents.length > 0) {
        setEvents((prev) => [...prev, ...newEvents].slice(-MAX_EVENTS));
      }
    }, TICK_MS);

    return () => clearInterval(id);
  }, [limit, prompt]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-background/85 backdrop-blur-[2px] px-6"
      role="dialog"
      aria-modal="true"
      aria-label="Pipeline in progress"
      aria-busy="true"
    >
      <div className="w-full max-w-xl rounded-[3px] border border-edge bg-surface px-8 py-10 shadow-[0_8px_40px_rgba(10,10,10,0.08)]">
        <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[.18em] text-muted-fg">
          Running pipeline
        </p>
        <h2 className="mb-2 font-serif text-[22px] leading-snug tracking-[-0.01em] text-fg line-clamp-2">
          {prompt}
        </h2>
        <p className="mb-8 font-mono text-[11px] text-muted-fg">
          This usually takes 30–90 seconds — hang tight.
        </p>

        <PipelineStageList
          status={snapshot.status}
          progress={snapshot}
          limit={limit}
        />

        {events.length > 0 && (
          <div className="mt-8 rounded-[3px] border border-edge bg-background p-4">
            <p className="mb-2 font-mono text-[9.5px] uppercase tracking-[.18em] text-muted-fg">
              Activity
            </p>
            <ul className="space-y-1" aria-live="polite">
              {events.map((ev, i) => (
                <li
                  key={`${ev}-${i}`}
                  className={
                    i === events.length - 1
                      ? "font-mono text-[11px] leading-relaxed text-fg"
                      : "font-mono text-[11px] leading-relaxed text-muted-fg"
                  }
                >
                  {ev}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
