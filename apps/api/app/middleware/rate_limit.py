"""Fixed-window rate limiting, backed by Redis so it holds across the
multiple worker processes Railway runs in production (an in-process
counter would only limit each worker individually).

Fails open: if Redis is unreachable, requests are allowed through and a
warning is logged — a rate limiter that can take the whole API down
whenever its backing store hiccups is worse than no rate limiter.
"""

import time
from collections.abc import Awaitable, Callable

import redis.asyncio as redis_asyncio
import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

logger = structlog.get_logger("app.rate_limit")

# Health/system checks are polled frequently by uptime monitors — never throttle them.
_EXEMPT_PREFIXES = ("/api/v1/system/health", "/docs", "/openapi.json")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: object,
        *,
        redis_url: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._redis_url = redis_url
        self._limit = limit
        self._window = window_seconds
        self._client: redis_asyncio.Redis | None = None

    def _get_client(self) -> redis_asyncio.Redis:
        if self._client is None:
            self._client = redis_asyncio.from_url(self._redis_url)  # type: ignore[no-untyped-call]
        return self._client

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.url.path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        client_host = request.client.host if request.client else "unknown"
        window_start = int(time.time() // self._window)
        key = f"ratelimit:{client_host}:{window_start}"

        try:
            client = self._get_client()
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, self._window)
        except Exception:  # noqa: BLE001 — fail open, never let Redis take the API down
            logger.warning("rate_limit.backend_unavailable", exc_info=True)
            return await call_next(request)

        if count > self._limit:
            return JSONResponse(
                status_code=429,
                content={
                    "success": False,
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests. Please slow down.",
                    },
                },
                headers={"Retry-After": str(self._window)},
            )

        return await call_next(request)
