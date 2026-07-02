import type { Lead } from "./api";

export type ScoreBucket = "high" | "mid" | "low";

export type FilterState = {
  minScore: number;
  maxScore: number;
  hasWebsite: boolean | null;
  industries: string[];
};

export type CohortStats = {
  count: number;
  avgScore: number;
  pctWebsite: number;
  pctPhone: number;
};

export type Cohort = {
  bucket: ScoreBucket;
  industry: string;
  label: string;
  leads: Lead[];
  stats: CohortStats;
};

export const DEFAULT_FILTERS: FilterState = {
  minScore: 0,
  maxScore: 1,
  hasWebsite: null,
  industries: [],
};

const BUCKET_ORDER: ScoreBucket[] = ["high", "mid", "low"];
const BUCKET_LABELS: Record<ScoreBucket, string> = {
  high: "High fit",
  mid: "Medium fit",
  low: "Low fit",
};

export function scoreBucket(score: number): ScoreBucket {
  if (score > 0.8) return "high";
  if (score >= 0.5) return "mid";
  return "low";
}

export function detectIndustry(lead: Lead): string {
  const raw = lead.place.category;
  if (!raw) return "Other";
  return raw
    .split(/[\s_-]+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(" ");
}

export function cohortStats(leads: Lead[]): CohortStats {
  const n = leads.length;
  if (n === 0) return { count: 0, avgScore: 0, pctWebsite: 0, pctPhone: 0 };
  const scores = leads.map((l) => l.verdict?.score ?? 0);
  const avgScore = scores.reduce((a, b) => a + b, 0) / n;
  const pctWebsite = leads.filter((l) => l.place.website).length / n;
  const pctPhone = leads.filter((l) => l.place.phone).length / n;
  return { count: n, avgScore, pctWebsite, pctPhone };
}

function applyFilters(leads: Lead[], filters: FilterState): Lead[] {
  return leads.filter((l) => {
    const score = l.verdict?.score ?? 0;
    if (score < filters.minScore || score > filters.maxScore) return false;
    if (filters.hasWebsite === true && !l.place.website) return false;
    if (filters.hasWebsite === false && l.place.website) return false;
    if (filters.industries.length > 0 && !filters.industries.includes(detectIndustry(l))) return false;
    return true;
  });
}

export function groupIntoCohorts(leads: Lead[], filters: FilterState = DEFAULT_FILTERS): Cohort[] {
  const qualified = leads.filter((l) => l.verdict?.is_qualified === true);
  const filtered = applyFilters(qualified, filters);

  const map = new Map<string, Lead[]>();
  for (const lead of filtered) {
    const key = `${scoreBucket(lead.verdict!.score)}::${detectIndustry(lead)}`;
    const existing = map.get(key);
    if (existing) existing.push(lead);
    else map.set(key, [lead]);
  }

  const cohorts: Cohort[] = [];
  for (const [key, cohortLeads] of map) {
    const [bucket, industry] = key.split("::") as [ScoreBucket, string];
    const stats = cohortStats(cohortLeads);
    const label = `${BUCKET_LABELS[bucket]} — ${industry} (${cohortLeads.length} lead${cohortLeads.length !== 1 ? "s" : ""})`;
    cohorts.push({ bucket, industry, label, leads: cohortLeads, stats });
  }

  return cohorts.sort((a, b) => {
    const bi = BUCKET_ORDER.indexOf(a.bucket) - BUCKET_ORDER.indexOf(b.bucket);
    return bi !== 0 ? bi : a.industry.localeCompare(b.industry);
  });
}

export function allIndustries(leads: Lead[]): string[] {
  const set = new Set<string>();
  for (const l of leads) {
    if (l.verdict?.is_qualified) set.add(detectIndustry(l));
  }
  return Array.from(set).sort();
}
