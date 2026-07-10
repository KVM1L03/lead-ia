"use client";

import { useSyncExternalStore } from "react";
import { MAPS_PROVIDERS, type MapsProvider } from "@/lib/mapsProviders";

export type Provider = MapsProvider;

const STORAGE_KEY = "lf_provider";

function subscribe(callback: () => void): () => void {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

function parseProvider(value: string | null): Provider {
  if (value !== null && (MAPS_PROVIDERS as readonly string[]).includes(value)) {
    return value as Provider;
  }
  return "mock";
}

function getSnapshot(): Provider {
  return parseProvider(localStorage.getItem(STORAGE_KEY));
}

function getServerSnapshot(): Provider {
  return "mock";
}

export function useProvider(): Provider {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

export function setProvider(next: Provider): void {
  localStorage.setItem(STORAGE_KEY, next);
  // Notify same-tab listeners (storage events only fire cross-tab natively)
  window.dispatchEvent(new Event("storage"));
}
