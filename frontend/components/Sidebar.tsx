"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProvider, setProvider } from "@/lib/useProvider";
import { MAPS_PROVIDERS, MAPS_PROVIDER_LABELS } from "@/lib/mapsProviders";

const NAV_LINKS = [
  { href: "/search", label: "New search" },
  { href: "/history", label: "History" },
] as const;

export function Sidebar({ demoMode = false }: { demoMode?: boolean }) {
  const pathname = usePathname();
  const provider = useProvider();

  function isActive(href: string) {
    return pathname === href || pathname.startsWith(href + "/");
  }

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-[220px] bg-background border-r border-edge flex flex-col z-40">
      {/* Brand */}
      <div className="px-6 pt-8 pb-6 border-b border-edge">
        <div className="flex items-center gap-2 mb-1">
          <Image
            src="/leadia-logo.png"
            alt="LeadIA"
            width={24}
            height={24}
            className="flex-none rounded-sm"
            priority
          />
          <span className="font-serif font-semibold text-[17px] leading-none text-fg tracking-[-0.01em]">
            LeadIA
          </span>
        </div>
        <p className="font-mono font-medium text-[9.5px] uppercase tracking-[.18em] text-muted-fg pl-[32px]">
          B2B Lead Engine
        </p>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 pt-4">
        <ul className="space-y-0.5">
          {NAV_LINKS.map(({ href, label }) => {
            const active = isActive(href);
            return (
              <li key={href}>
                <Link
                  href={href}
                  className={[
                    "flex items-center py-2 rounded-[3px] text-[13px] font-sans font-medium leading-none transition-colors border-l-2 pl-[10px] pr-3",
                    active
                      ? "text-fg bg-brand-soft border-brand"
                      : "text-subtle hover:text-fg hover:bg-skeleton border-transparent",
                  ].join(" ")}
                >
                  {label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Settings */}
      <div className="px-6 py-6 border-t border-edge">
        <p className="font-sans font-medium text-[11px] uppercase tracking-[.16em] text-muted-fg mb-3">
          Provider
        </p>
        {demoMode ? (
          <p className="font-mono text-[12px] text-fg">SerpAPI</p>
        ) : (
          <div className="flex flex-col gap-1 rounded-[3px] border border-edge-input overflow-hidden text-[11px] font-sans font-medium">
            {MAPS_PROVIDERS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => setProvider(p)}
                className={[
                  "py-1.5 px-2 text-left transition-colors",
                  provider === p
                    ? "bg-brand text-white"
                    : "bg-background text-subtle hover:text-fg",
                ].join(" ")}
              >
                {MAPS_PROVIDER_LABELS[p]}
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  );
}
