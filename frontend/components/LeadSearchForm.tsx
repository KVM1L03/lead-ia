"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { Toast } from "@base-ui/react/toast";
import { startSearch } from "@/app/actions";
import type { Lead } from "@/lib/api";
import { useProvider, setProvider } from "@/lib/useProvider";
import { cn } from "@/lib/utils";
import { LeadCohortTable } from "./LeadCohortTable";
import { SyncProgressOverlay } from "./SyncProgressOverlay";

const LIMIT_MIN = 10;
const LIMIT_MAX_FULL = 200;
const LIMIT_MAX_DEMO = 20;
const LIMIT_DEFAULT = 50;
const LIMIT_DEFAULT_DEMO = 10;

export function LeadSearchForm({ demoMode = false }: { demoMode?: boolean }) {
  const [prompt, setPrompt] = useState("");
  const [senderContext, setSenderContext] = useState("");
  const limitMax = demoMode ? LIMIT_MAX_DEMO : LIMIT_MAX_FULL;
  const [limit, setLimit] = useState(demoMode ? LIMIT_DEFAULT_DEMO : LIMIT_DEFAULT);
  const [isPending, startTransition] = useTransition();
  const [syncResults, setSyncResults] = useState<{ runId: string; leads: Lead[] } | null>(null);
  const [pendingPrompt, setPendingPrompt] = useState("");
  const router = useRouter();
  const { add: addToast } = Toast.useToastManager();
  const provider = useProvider();

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setSyncResults(null);
    setPendingPrompt(prompt.trim());

    if (!prompt.trim()) {
      addToast({
        title: "Prompt required",
        description: "Describe the leads you want to find.",
        type: "error",
      });
      return;
    }

    startTransition(async () => {
      const result = await startSearch(prompt.trim(), limit, senderContext.trim());
      if (result.status === "success") {
        if (result.mode === "sync") {
          setSyncResults({ runId: result.runId, leads: result.results });
        } else {
          router.push(`/runs/${result.runId}`);
        }
      } else {
        addToast({
          title: "Search failed",
          description: result.message,
          type: "error",
        });
      }
    });
  }

  const disabled = isPending;

  // Inline sync results view — shown after a sync pipeline completes.
  if (syncResults !== null) {
    return (
      <section className="px-8 py-10">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <p className="mb-1 font-mono text-[11px] font-medium uppercase tracking-[.18em] text-muted-fg">
              Results
            </p>
            <h2 className="font-serif text-[28px] leading-[1.35] tracking-[-0.015em] text-fg">
              {syncResults.leads.length} lead{syncResults.leads.length !== 1 ? "s" : ""} found
            </h2>
          </div>
          <button
            type="button"
            onClick={() => setSyncResults(null)}
            className="inline-flex items-center gap-2 rounded-[3px] border border-edge px-4 py-2 font-sans text-[13px] font-medium text-fg hover:bg-surface transition-colors"
          >
            ← New search
          </button>
        </div>
        {syncResults.leads.length === 0 ? (
          <div className="rounded-[3px] border border-edge bg-surface px-6 py-10 text-center">
            <p className="font-sans text-[13px] text-muted-fg">
              No leads matched your criteria. Try a broader prompt.
            </p>
          </div>
        ) : (
          <LeadCohortTable leads={syncResults.leads} runId={syncResults.runId} />
        )}
      </section>
    );
  }

  return (
    <section className="relative max-w-[760px] mx-auto px-8 py-[13vh]">
      {isPending && (
        <SyncProgressOverlay prompt={pendingPrompt} limit={limit} />
      )}
      {/* Label */}
      <p className="font-sans font-medium text-[11px] uppercase tracking-[.18em] text-muted-fg mb-[34px]">
        New run
      </p>

      {/* Headline */}
      <div className="font-serif text-[40px] leading-[1.22] tracking-[-0.01em] mb-[18px]">
        Find{" "}
        <span className="text-brand font-mono text-[38px]" aria-hidden="true">
          {limit}
        </span>{" "}
        B2B leads for
      </div>

      <form onSubmit={handleSubmit} aria-label="Lead search">
        {/* Prompt — styled like the design's editorial input */}
        <textarea
          id="prompt"
          aria-label="Describe the leads you want"
          placeholder="B2B SaaS companies selling scheduling software, targeting dental practices in Warsaw"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={disabled}
          rows={3}
          className={cn(
            "w-full resize-none bg-transparent outline-none",
            "border-b border-[#161613] pb-2 pt-2",
            "font-serif text-[24px] leading-[1.35] text-fg placeholder:text-[#B0AEA4]",
            "focus:border-brand transition-colors",
            "disabled:opacity-50",
          )}
        />

        {/* Sender context */}
        <div className="mt-8">
          <label
            htmlFor="sender-context"
            className="block font-sans font-medium text-[11px] uppercase tracking-[.14em] text-subtle mb-2"
          >
            Who you are
          </label>
          <textarea
            id="sender-context"
            placeholder="e.g. I run a dental practice management SaaS and help clinics reduce no-shows"
            value={senderContext}
            onChange={(e) => setSenderContext(e.target.value)}
            disabled={disabled}
            rows={2}
            className={cn(
              "w-full resize-none bg-transparent outline-none",
              "border-b border-edge-input pb-2 pt-1",
              "font-sans text-[14px] leading-[1.6] text-fg placeholder:text-muted-fg",
              "focus:border-brand transition-colors",
              "disabled:opacity-50",
            )}
          />
        </div>

        {/* Controls row: slider + provider toggle */}
        <div className="flex items-end justify-between gap-10 mt-[54px]">
          {/* Slider */}
          <div className="flex-1">
            <div className="flex items-baseline justify-between mb-3">
              <span className="font-sans font-medium text-[11px] uppercase tracking-[.14em] text-subtle">
                Result count
              </span>
              <span className="font-serif text-[22px] leading-none tabular-nums text-fg">
                {limit}
              </span>
            </div>
            <input
              type="range"
              min={LIMIT_MIN}
              max={limitMax}
              step={demoMode ? 5 : 10}
              value={limit}
              onChange={(e) => setLimit(Number(e.target.value))}
              disabled={disabled}
              aria-label="Result count"
              className="w-full h-1 accent-[#c8742e] disabled:opacity-50"
            />
            <div className="flex justify-between mt-[7px] font-mono text-[10px] text-muted-fg">
              <span>{LIMIT_MIN}</span>
              <span>{limitMax}</span>
            </div>
          </div>

          {/* Provider toggle — hidden in demo mode (SerpAPI only) */}
          {!demoMode && (
            <div>
              <p className="font-sans font-medium text-[11px] uppercase tracking-[.14em] text-subtle mb-3">
                Source
              </p>
              <div className="inline-flex border border-edge-input rounded-[4px] overflow-hidden text-[11px] font-sans font-medium">
                {(["serpapi", "mock"] as const).map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setProvider(p)}
                    disabled={disabled}
                    className={cn(
                      "px-3 py-1.5 transition-colors",
                      provider === p
                        ? "bg-brand text-white"
                        : "bg-background text-subtle hover:text-fg disabled:opacity-50",
                    )}
                  >
                    {p === "serpapi" ? "SerpAPI" : "Mock"}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Submit row */}
        <div className="flex items-center gap-[22px] mt-[50px]">
          <button
            type="submit"
            disabled={disabled}
            className={cn(
              "inline-flex items-center gap-2 bg-brand text-white",
              "font-sans font-semibold text-[14px] leading-none",
              "rounded-[3px] px-6 py-[11px]",
              "hover:brightness-90 transition-[filter]",
              "disabled:opacity-50 disabled:cursor-not-allowed",
            )}
          >
            {isPending ? "Running…" : "Start search"}
            {!isPending && <span className="font-mono text-[14px]">→</span>}
          </button>
          {!isPending && (
            <span className="font-mono text-[12px] leading-[1.5] text-muted-fg">
              cheap-model qualifier
            </span>
          )}
        </div>
      </form>
    </section>
  );
}
