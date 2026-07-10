import type { Lead } from "./api";

const COLUMNS = [
  "business_name",
  "address",
  "website",
  "phone",
  "category",
  "rating",
  "review_count",
  "qualifier_score",
  "qualifier_reasoning",
  "email_subject",
  "email_body",
  "personalization_hooks",
] as const;

// RFC 4180 QUOTE_MINIMAL: quote only when field contains delimiter, double-quote, or newline.
function csvField(v: string): string {
  if (v.includes(",") || v.includes('"') || v.includes("\n") || v.includes("\r")) {
    return `"${v.replace(/"/g, '""')}"`;
  }
  return v;
}

export function leadsToCSV(leads: Lead[]): string {
  const lines: string[] = [COLUMNS.join(",")];
  for (const lead of leads) {
    if (lead.decision !== "approved") continue;
    lines.push(
      [
        csvField(lead.place.name),
        csvField(lead.place.address),
        csvField(lead.place.website ?? ""),
        csvField(lead.place.phone ?? ""),
        csvField(lead.place.category),
        lead.place.rating != null ? String(lead.place.rating) : "",
        lead.place.review_count != null ? String(lead.place.review_count) : "",
        lead.verdict ? String(lead.verdict.score) : "",
        csvField(lead.verdict?.reasoning ?? ""),
        csvField(lead.email?.subject ?? ""),
        csvField(lead.email?.body ?? ""),
        csvField(lead.email?.personalization_hooks.join("; ") ?? ""),
      ].join(","),
    );
  }
  return lines.join("\r\n") + "\r\n";
}
