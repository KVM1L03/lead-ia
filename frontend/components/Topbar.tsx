"use client";

import { useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type HealthStatus = "healthy" | "unhealthy" | "unknown";

function HealthDot({ status }: { status: HealthStatus }) {
  const colors: Record<HealthStatus, string> = {
    healthy: "bg-green-500",
    unhealthy: "bg-red-500",
    unknown: "bg-edge-input",
  };
  const labels: Record<HealthStatus, string> = {
    healthy: "API online",
    unhealthy: "API offline",
    unknown: "Checking API…",
  };

  return (
    <span
      title={labels[status]}
      className={`inline-block w-2 h-2 rounded-full ${colors[status]} transition-colors`}
    />
  );
}

export function Topbar() {
  const [health, setHealth] = useState<HealthStatus>("unknown");

  useEffect(() => {
    let cancelled = false;

    async function check() {
      try {
        const res = await fetch(`${API_BASE}/api/health`, {
          signal: AbortSignal.timeout(3000),
        });
        if (!cancelled) setHealth(res.ok ? "healthy" : "unhealthy");
      } catch {
        if (!cancelled) setHealth("unhealthy");
      }
    }

    check();
    const id = setInterval(check, 10_000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  return (
    <header
      className="sticky top-0 z-30 flex items-center justify-end h-[60px] px-6 gap-5 border-b border-edge"
      style={{ background: "rgba(250,250,247,.85)", backdropFilter: "blur(10px)" }}
    >
      <a
        href="http://localhost:3030"
        target="_blank"
        rel="noopener noreferrer"
        className="font-sans font-medium text-[12px] text-muted-fg hover:text-fg transition-colors"
      >
        Langfuse
      </a>

      <span className="w-px h-3.5 bg-edge" aria-hidden="true" />

      <a
        href="http://localhost:8085"
        target="_blank"
        rel="noopener noreferrer"
        className="font-sans font-medium text-[12px] text-muted-fg hover:text-fg transition-colors"
      >
        Temporal UI
      </a>

      <span className="w-px h-3.5 bg-edge" aria-hidden="true" />

      <HealthDot status={health} />
    </header>
  );
}
