export const MAPS_PROVIDERS = ["mock", "serpapi", "google_places"] as const;

export type MapsProvider = (typeof MAPS_PROVIDERS)[number];

export const MAPS_PROVIDER_LABELS: Record<MapsProvider, string> = {
  mock: "Mock",
  serpapi: "SerpAPI",
  google_places: "Google Places",
};
