// Pure logic for RunProgressView — extracted so vitest can test without DOM.

export type StageState = "pending" | "active" | "done";

export type Stage = {
  label: string;
  state: StageState;
  current: number;
  total: number;
};

export type RunStatus =
  | "scraping"
  | "qualifying"
  | "generating"
  | "completed"
  | "failed";

const STAGE_ACTIVE_STATUS: RunStatus[] = ["scraping", "qualifying", "generating"];

export function computeStages(
  status: string,
  progress: { scraped: number; qualified: number; emails_generated: number },
  limit: number,
): Stage[] {
  function stageState(stageIdx: number): StageState {
    const activeIdx = STAGE_ACTIVE_STATUS.indexOf(status as RunStatus);
    if (activeIdx === stageIdx) return "active";
    if (activeIdx > stageIdx || status === "completed" || status === "failed") return "done";
    return "pending";
  }

  return [
    {
      label: "Scraping Maps",
      state: stageState(0),
      current: progress.scraped,
      total: limit,
    },
    {
      label: "Qualifying leads",
      state: stageState(1),
      current: progress.qualified,
      total: progress.scraped || limit,
    },
    {
      label: "Drafting emails",
      state: stageState(2),
      current: progress.emails_generated,
      total: progress.qualified || progress.scraped || 1,
    },
  ];
}

export type ProgressSnapshot = {
  status: string;
  scraped: number;
  qualified: number;
  emails_generated: number;
};

export function synthesizeEvents(
  prev: ProgressSnapshot,
  next: ProgressSnapshot,
): string[] {
  const events: string[] = [];

  if (prev.status !== next.status) {
    if (next.status === "qualifying") events.push(`Scraped ${next.scraped} places — qualifying…`);
    else if (next.status === "generating") events.push(`Qualified ${next.qualified} leads — drafting emails…`);
    else if (next.status === "completed") events.push(`Done — ${next.emails_generated} emails ready`);
    else if (next.status === "failed") events.push("Run failed");
  } else {
    if (next.status === "scraping" && next.scraped > prev.scraped) {
      events.push(`Found ${next.scraped} place${next.scraped !== 1 ? "s" : ""}`);
    }
    if (next.status === "qualifying" && next.qualified > prev.qualified) {
      events.push(`Qualified ${next.qualified} / ${next.scraped}`);
    }
    if (next.status === "generating" && next.emails_generated > prev.emails_generated) {
      events.push(`Drafted email ${next.emails_generated} / ${next.qualified}`);
    }
  }

  return events;
}

export const TERMINAL_STATUSES = new Set<string>(["completed", "failed"]);
