import Link from "next/link";

export default function Home() {
  return (
    <section className="flex flex-col flex-1 items-center justify-center min-h-[calc(100vh-60px)] px-8">
      <div className="text-center max-w-[340px]">
        <p className="font-mono font-medium text-[11px] uppercase tracking-[.18em] text-muted-fg mb-10">
          No runs yet
        </p>
        <h1 className="font-serif text-[30px] leading-[1.35] tracking-[-0.015em] text-fg mb-10">
          Start a search to find your first cohort of leads.
        </h1>
        <Link
          href="/search"
          className="inline-flex items-center gap-2 bg-brand text-white text-[13px] font-sans font-medium rounded-[3px] px-5 py-2.5 hover:brightness-90 transition-[filter]"
        >
          New search
        </Link>
      </div>
    </section>
  );
}
