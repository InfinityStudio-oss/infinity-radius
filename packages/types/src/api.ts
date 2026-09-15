/** Generic envelope shapes shared between the FastAPI backend and the Next.js frontend. */
export interface ApiError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export type ApiResult<T> = { data: T; error: null } | { data: null; error: ApiError };
