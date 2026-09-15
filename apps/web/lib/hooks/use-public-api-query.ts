"use client";

import { useCallback, useEffect, useState } from "react";
import { apiFetch, ApiClientError } from "@/lib/api-client";

export type ApiQueryState = "loading" | "error" | "success";

export interface PublicApiQueryResult<T> {
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
 * Same contract as useApiQuery, without Supabase auth — for unauthenticated,
 * public-facing surfaces like the captive portal. See useApiQuery for why
 * `state` is derived rather than set imperatively at the top of the effect.
 */
export function usePublicApiQuery<T>(path: string | null): PublicApiQueryResult<T> {
  const [attempt, setAttempt] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);

  const refetch = useCallback(() => setAttempt((n) => n + 1), []);

  const requestKey = path ? `${path}::${attempt}` : null;

  useEffect(() => {
    if (!requestKey || !path) return;

    let active = true;
    const controller = new AbortController();

    apiFetch<T>(path, { signal: controller.signal })
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
    // eslint-disable-next-line react-hooks/exhaustive-deps -- requestKey already encodes path/attempt
  }, [requestKey]);

  const isCurrent = settled?.key === requestKey;

  return {
    state: !requestKey || !isCurrent ? "loading" : settled.error ? "error" : "success",
    data: isCurrent ? settled.data : null,
    error: isCurrent ? settled.error : null,
    refetch,
  };
}
