"""Assigns every request a request ID (reusing an inbound `X-Request-ID`
header if the caller already set one, e.g. a load balancer), binds it into
structlog's contextvars for the lifetime of the request, and echoes it back
on the response — so a client can quote it back for support/debugging and
every log line for that request carries it automatically.
"""

import time
import uuid
from collections.abc import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        started_at = time.perf_counter()
        logger.info("request.started")

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.exception("request.failed", duration_ms=duration_ms)
            raise

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        logger.info(
            "request.completed",
            status_code=response.status_code,
            duration_ms=duration_ms,
        )

        response.headers[REQUEST_ID_HEADER] = request_id
        return response
