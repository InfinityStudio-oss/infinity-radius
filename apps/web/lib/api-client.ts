import { clientEnv } from "@/lib/env";

export class ApiClientError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

export interface ApiFetchOptions {
  accessToken?: string | null;
  signal?: AbortSignal;
}

/**
 * Thin fetch wrapper around the FastAPI backend. Throws ApiClientError on
 * any non-2xx response or network failure — callers translate that into an
 * "error"/"unavailable" UI state, never a silently substituted empty result.
 */
export async function apiFetch<T>(path: string, options: ApiFetchOptions = {}): Promise<T> {
  const url = `${clientEnv.NEXT_PUBLIC_API_BASE_URL}${path}`;
  const headers: Record<string, string> = { Accept: "application/json" };

  if (options.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }

  let response: Response;
  try {
    response = await fetch(url, { headers, signal: options.signal });
  } catch (cause) {
    throw new ApiClientError(cause instanceof Error ? cause.message : "Network request failed");
  }

  if (!response.ok) {
    throw new ApiClientError(`Request to ${path} failed with ${response.status}`, response.status);
  }

  return (await response.json()) as T;
}

export interface ApiMutateOptions {
  accessToken?: string | null;
  method?: "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
}

/**
 * POST/PUT/PATCH/DELETE against the FastAPI backend. Like apiFetch, throws
 * ApiClientError on any non-2xx response — the error's `.detail` (parsed
 * from the API's `{success:false,error:{code,message}}` envelope when
 * present) lets callers show the backend's actual validation message
 * instead of a generic failure.
 */
export async function apiMutate<T>(path: string, options: ApiMutateOptions = {}): Promise<T> {
  const url = `${clientEnv.NEXT_PUBLIC_API_BASE_URL}${path}`;
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.accessToken) {
    headers.Authorization = `Bearer ${options.accessToken}`;
  }
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method: options.method ?? "POST",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch (cause) {
    throw new ApiClientError(cause instanceof Error ? cause.message : "Network request failed");
  }

  if (!response.ok) {
    const detail = await response
      .json()
      .then((json: { error?: { message?: string } }) => json.error?.message)
      .catch(() => undefined);
    throw new ApiClientError(
      detail ?? `Request to ${path} failed with ${response.status}`,
      response.status,
    );
  }

  return (await response.json()) as T;
}
