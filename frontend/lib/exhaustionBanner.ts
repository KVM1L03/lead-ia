// Pure logic for the Backfill exhaustion banner — extracted so vitest can test
// without DOM. See .scratch/backfill/issues/04-exhaustion-banner-review-ui.md.

export type ExhaustionBannerInput = {
  backfillExhausted: boolean;
  qualified: number;
  limit: number;
  triedCities: string[];
  triedIndustries: string[];
};

function joinWithAnd(items: string[]): string {
  if (items.length === 1) return items[0];
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

/** Returns the banner copy, or null when nothing should render. */
export function buildExhaustionBannerText(input: ExhaustionBannerInput): string | null {
  if (!input.backfillExhausted) return null;

  const tried = [
    ...input.triedCities,
    ...input.triedIndustries.map((i) => `'${i}'`),
  ];

  const prefix = `Found ${input.qualified}/${input.limit}`;
  if (tried.length === 0) return `${prefix} — no further matches found.`;

  return `${prefix} — also checked ${joinWithAnd(tried)}, no further matches.`;
}
