"""Every error response — whatever raised it — comes back in the same
shape: `{"success": false, "error": {"code", "message", "request_id"}}`.
Route handlers/services raise ApiError (or a subclass) for domain errors;
FastAPI's own HTTPException, Pydantic's RequestValidationError, and any
uncaught exception are all normalized to the same envelope by the handlers
registered in app.main.
"""

import structlog
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = structlog.get_logger("app.errors")


class ApiError(Exception):
    """Base class for domain errors a service/repository raises on purpose.
    Route handlers let these propagate — they're turned into the standard
    error envelope by api_error_handler, never caught and reformatted
    per-route.
    """

    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        retry_after_seconds: int | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds


class NotFoundError(ApiError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(code="not_found", message=message, status_code=status.HTTP_404_NOT_FOUND)


class ConflictError(ApiError):
    def __init__(self, message: str = "Resource already exists") -> None:
        super().__init__(code="conflict", message=message, status_code=status.HTTP_409_CONFLICT)


class DomainValidationError(ApiError):
    """A validation failure that depends on business rules Pydantic's field
    validation can't express alone (e.g. a phone number that's syntactically
    a string but not a valid Tanzania number)."""

    def __init__(self, message: str) -> None:
        super().__init__(
            code="validation_error",
            message=message,
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )


class RateLimitedError(ApiError):
    """A per-resource cooldown/cap, distinct from the global IP-based rate
    limit middleware — e.g. the withdrawal OTP resend cooldown. Carries
    retry_after_seconds so the client can show an accurate countdown."""

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(
            code="rate_limited",
            message=message,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            retry_after_seconds=retry_after_seconds,
        )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "-")


def _error_body(*, code: str, message: str, request_id: str) -> dict[str, object]:
    return {
        "success": False,
        "error": {"code": code, "message": message, "request_id": request_id},
    }


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    headers = (
        {"Retry-After": str(exc.retry_after_seconds)}
        if exc.retry_after_seconds is not None
        else None
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(code=exc.code, message=exc.message, request_id=_request_id(request)),
        headers=headers,
    )


_HTTP_STATUS_CODES: dict[int, str] = {
    status.HTTP_400_BAD_REQUEST: "bad_request",
    status.HTTP_401_UNAUTHORIZED: "unauthorized",
    status.HTTP_403_FORBIDDEN: "forbidden",
    status.HTTP_404_NOT_FOUND: "not_found",
    status.HTTP_409_CONFLICT: "conflict",
    status.HTTP_422_UNPROCESSABLE_CONTENT: "validation_error",
    status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
}


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    code = _HTTP_STATUS_CODES.get(exc.status_code, "http_error")
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(
            code=code, message=str(exc.detail), request_id=_request_id(request)
        ),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    first_error = exc.errors()[0] if exc.errors() else None
    message = (
        f"{'.'.join(str(loc) for loc in first_error['loc'])}: {first_error['msg']}"
        if first_error
        else "Request validation failed"
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content=_error_body(
            code="validation_error", message=message, request_id=_request_id(request)
        ),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.exception("request.unhandled_exception", request_id=request_id)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=_error_body(
            code="internal_error",
            message="An unexpected error occurred.",
            request_id=request_id,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
