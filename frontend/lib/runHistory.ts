export type RunStatus = "scraping" | "qualifying" | "generating" | "completed" | "failed";

export type StatusConfig = {
  label: string;
  className: string;
};

export function formatRelativeTime(date: Date, now: Date = new Date()): string {
  const diffMs = now.getTime() - date.getTime();
  const diffSec = Math.floor(diffMs / 1000);
  const diffMin = Math.floor(diffSec / 60);
  const diffHr = Math.floor(diffMin / 60);
  const diffDay = Math.floor(diffHr / 24);

  if (diffSec < 60) return "just now";
  if (diffMin < 60) return `${diffMin} minute${diffMin !== 1 ? "s" : ""} ago`;
  if (diffHr < 24) return `${diffHr} hour${diffHr !== 1 ? "s" : ""} ago`;
  if (diffDay < 30) return `${diffDay} day${diffDay !== 1 ? "s" : ""} ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

export function approvalRate(approved: number, total: number): number | null {
  if (total === 0) return null;
  return approved / total;
}

export function statusConfig(status: string): StatusConfig {
  switch (status) {
    case "completed":
      return { label: "Completed", className: "bg-success-soft text-success-fg border-success/30" };
    case "failed":
      return { label: "Failed", className: "bg-reject-soft text-reject border-reject/30" };
    case "scraping":
      return { label: "Scraping", className: "bg-warning-soft text-warning-fg border-warning/40" };
    case "qualifying":
      return { label: "Qualifying", className: "bg-warning-soft text-warning-fg border-warning/40" };
    case "generating":
      return { label: "Generating", className: "bg-warning-soft text-warning-fg border-warning/40" };
    default:
      return { label: status, className: "bg-skeleton text-subtle border-edge" };
  }
}

export function isTerminal(status: string): boolean {
  return status === "completed" || status === "failed";
}
