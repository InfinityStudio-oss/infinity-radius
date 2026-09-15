"""Exercises RateLimitMiddleware in isolation against a tiny limit — the
real app's limit (120/min) would make a real test either slow or flaky, so
this builds a minimal Starlette app with the same middleware and a limit
of 2 to prove the 429 path (and its envelope) for real."""

import pytest
import redis as redis_sync
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.core.config import get_settings
from app.middleware.rate_limit import RateLimitMiddleware


async def _ok(request: object) -> PlainTextResponse:
    return PlainTextResponse("ok")


def _make_client(*, limit: int) -> TestClient:
    app = Starlette(routes=[Route("/ping", _ok)])
    app.add_middleware(
        RateLimitMiddleware,
        redis_url=str(get_settings().redis_url),
        limit=limit,
        window_seconds=60,
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limit_counters() -> None:
    """The middleware keys its fixed window on client_host, and every
    TestClient in this suite (this file's and the full app's) reports the
    same host ("testclient"), so counters from earlier tests in the same
    60s window would otherwise bleed into these assertions."""
    client = redis_sync.from_url(str(get_settings().redis_url))  # type: ignore[no-untyped-call]
    for key in client.scan_iter("ratelimit:testclient:*"):
        client.delete(key)
    client.close()


def test_requests_under_the_limit_pass_through() -> None:
    # Entered as a context manager so every request in this test shares one
    # event loop/portal — matching how a real (single, persistent-loop)
    # ASGI server runs the app, and how the middleware's cached async Redis
    # client is meant to be reused. Standalone (non-`with`) TestClient calls
    # each spin up their own throwaway loop, which stale-binds that cached
    # client and makes the limiter fail open on later calls.
    with _make_client(limit=5) as client:
        for _ in range(5):
            assert client.get("/ping").status_code == 200


def test_requests_over_the_limit_are_rejected_with_structured_envelope() -> None:
    with _make_client(limit=2) as client:
        assert client.get("/ping").status_code == 200
        assert client.get("/ping").status_code == 200

        response = client.get("/ping")

        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"
        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "rate_limited"


def test_health_path_is_exempt_from_rate_limiting() -> None:
    app = Starlette(routes=[Route("/api/v1/system/health/database", _ok)])
    app.add_middleware(
        RateLimitMiddleware,
        redis_url=str(get_settings().redis_url),
        limit=1,
        window_seconds=60,
    )
    client = TestClient(app)

    for _ in range(3):
        assert client.get("/api/v1/system/health/database").status_code == 200
