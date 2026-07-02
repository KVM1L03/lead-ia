"use client";

import { useSyncExternalStore } from "react";

export type Provider = "serpapi" | "mock";

const STORAGE_KEY = "lf_provider";

function subscribe(callback: () => void): () => void {
  window.addEventListener("storage", callback);
  return () => window.removeEventListener("storage", callback);
}

function getSnapshot(): Provider {
  return localStorage.getItem(STORAGE_KEY) === "serpapi" ? "serpapi" : "mock";
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
