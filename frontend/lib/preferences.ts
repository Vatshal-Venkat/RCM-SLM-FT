"use client";

import { useSyncExternalStore } from "react";

/** Copilot preferences, kept in this browser only (Settings page). null = use the backend default. */
export interface CopilotPrefs {
  useRag: boolean;
  temperature: number | null;
  maxTokens: number | null;
}

export const DEFAULT_PREFS: CopilotPrefs = { useRag: true, temperature: null, maxTokens: null };

const KEY = "rcm.copilot.prefs";
const listeners = new Set<() => void>();
let cache: CopilotPrefs | null = null;

/** Current preferences outside React rendering (e.g. inside an effect). */
export function getPrefs(): CopilotPrefs {
  return read();
}

function read(): CopilotPrefs {
  if (cache) return cache;
  try {
    cache = { ...DEFAULT_PREFS, ...JSON.parse(localStorage.getItem(KEY) ?? "{}") };
  } catch {
    cache = DEFAULT_PREFS;
  }
  return cache as CopilotPrefs;
}

export function savePrefs(p: CopilotPrefs): void {
  cache = p;
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* storage unavailable: keep for this session only */
  }
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

export function usePrefs(): CopilotPrefs {
  return useSyncExternalStore(subscribe, read, () => DEFAULT_PREFS);
}
