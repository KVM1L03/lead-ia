import { computeStages, type Stage } from "@/lib/runProgress";
import { cn } from "@/lib/utils";

export type { Stage };

function StageIndicator({
  state,
  index,
}: {
  state: Stage["state"];
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
          <path
            d="M1.5 6.5 4.5 9.5 10.5 3"
            stroke="currentColor"
            strokeWidth="1.5"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
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
  state: Stage["state"];
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

export function PipelineStageRow({ stage, index }: { stage: Stage; index: number }) {
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

export function PipelineStageList({
  status,
  progress,
  limit,
}: {
  status: string;
  progress: { scraped: number; qualified: number; emails_generated: number };
  limit: number;
}) {
  const stages = computeStages(status, progress, limit);
  return (
    <div className="flex flex-col gap-6">
      {stages.map((stage, i) => (
        <PipelineStageRow key={stage.label} stage={stage} index={i} />
      ))}
    </div>
  );
}
