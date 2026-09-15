"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, ApiClientError } from "@/lib/api-client";
import { useAccessToken } from "@/lib/hooks/use-access-token";

export type ApiQueryState = "loading" | "error" | "success";

export interface ApiQueryResult<T> {
  state: ApiQueryState;
  data: T | null;
  error: ApiClientError | null;
  refetch: () => void;
}

interface Settled<T> {
  key: string;
  data: T | null;
  error: ApiClientError | null;
}

/**
 * Fetches `path` against the FastAPI backend, attaching the current
 * Supabase session token. Pass `path: null` to skip fetching (e.g. while
 * the token isn't ready yet) — the hook stays in "loading" until a path is
 * provided.
 *
 * `state` is derived by comparing the settled result's key against the
 * current request key, rather than set imperatively at the top of the
 * effect — setState only ever happens from the fetch's own callbacks.
 */
export function useApiQuery<T>(path: string | null): ApiQueryResult<T> {
  const { token, ready } = useAccessToken();
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);

  const refetch = useCallback(() => setAttempt((n) => n + 1), []);

  const requestKey = ready && path ? `${path}::${token ?? ""}::${attempt}` : null;

  useEffect(() => {
    if (!requestKey || !path) return;

    let active = true;
    const controller = new AbortController();

    apiFetch<T>(path, { accessToken: token, signal: controller.signal })
      .then((result) => {
        if (!active) return;
        setSettled({ key: requestKey, data: result, error: null });
      })
      .catch((err: unknown) => {
        if (!active) return;
        setSettled({
          key: requestKey,
          data: null,
          error:
            err instanceof ApiClientError
              ? err
              : new ApiClientError("Unexpected error loading data"),
        });
      });

    return () => {
      active = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- requestKey already encodes path/token/attempt
  }, [requestKey]);

  const isCurrent = settled?.key === requestKey;

  return {
    state: !requestKey || !isCurrent ? "loading" : settled.error ? "error" : "success",
    data: isCurrent ? settled.data : null,
    error: isCurrent ? settled.error : null,
    refetch,
  };
}
