import { buildExhaustionBannerText, type ExhaustionBannerInput } from "@/lib/exhaustionBanner";

export function ExhaustionBanner(props: ExhaustionBannerInput) {
  const text = buildExhaustionBannerText(props);
  if (text === null) return null;

  return (
    <div className="mb-5 flex items-start gap-2.5 rounded-2xl border border-glass-edge bg-glass backdrop-blur-md px-4 py-3">
      <svg
        viewBox="0 0 16 16"
        aria-hidden="true"
        className="mt-0.5 h-4 w-4 shrink-0 fill-none stroke-current stroke-[1.8] text-muted-fg"
      >
        <circle cx="8" cy="8" r="6.5" />
        <path d="M8 7.25v3.75M8 5.25v.01" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      <p className="font-sans text-[12.5px] leading-relaxed text-fg">{text}</p>
    </div>
  );
}
