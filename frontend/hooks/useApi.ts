"use client";

import { useCallback, useEffect, useState } from "react";

import { apiGet } from "@/lib/api";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

/** Fetch `path` whenever it changes; abort in-flight requests on change/unmount. */
export function useApi<T>(path: string | null): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(path));
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    if (!path) return;
    const ctrl = new AbortController();
    setLoading(true);
    setError(null);
    apiGet<T>(path, ctrl.signal)
      .then((d) => setData(d))
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message || "Request failed");
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoading(false);
      });
    return () => ctrl.abort();
  }, [path, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}
