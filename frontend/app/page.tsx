import Link from "next/link";

export default function Home() {
  return (
    <section className="flex flex-col flex-1 items-center justify-center min-h-[calc(100vh-60px)] px-8">
      <div className="text-center max-w-[420px] rounded-3xl border border-glass-edge bg-glass backdrop-blur-xl shadow-[0_10px_36px_rgba(0,0,0,.05)] px-10 py-11">
        <div className="mx-auto mb-6 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-soft">
          <svg
            width="23"
            height="23"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            className="text-brand"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m21 21-4.3-4.3" />
          </svg>
        </div>
        <p className="font-mono font-medium text-[11px] uppercase tracking-[.18em] text-muted-fg mb-4">
          No runs yet
        </p>
        <h1 className="font-serif text-[26px] leading-[1.35] tracking-[-0.015em] text-fg mb-8">
          Start a search to find your first cohort of leads.
        </h1>
        <Link
          href="/search"
          className="inline-flex items-center gap-2 bg-brand text-white text-[14px] font-sans font-semibold rounded-2xl px-6 py-3 shadow-[0_8px_22px_rgba(200,116,46,.32)] hover:scale-[1.02] transition-transform"
        >
          New search
        </Link>
      </div>
    </section>
  );
}
