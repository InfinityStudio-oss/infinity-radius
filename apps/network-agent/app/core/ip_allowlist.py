"""Restricts every request (except /health) to Railway's static outbound
IPs, on top of (never instead of) request signature verification —
defense in depth: a leaked signing key alone shouldn't be enough to reach
this agent from anywhere on the internet.

Caddy (infrastructure/caddy/Caddyfile) reverse-proxies to this agent over
localhost and forwards the real client IP via X-Forwarded-For — only that
header is trusted, and only because the immediate TCP peer is always
Caddy on 127.0.0.1 in production. If this agent is ever run without a
reverse proxy in front of it (e.g. bare `uvicorn` in local dev),
request.client.host is used instead.
"""

import ipaddress

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import get_network_agent_settings

logger = structlog.get_logger("agent.ip_allowlist")

_EXEMPT_PATHS = ("/health",)
_TRUSTED_PROXY_HOSTS = ("127.0.0.1", "::1")


def _client_ip(request: Request) -> str | None:
    direct_host = request.client.host if request.client else None
    if direct_host in _TRUSTED_PROXY_HOSTS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Caddy appends the real client; the first entry is the
            # original client even through multiple proxies.
            return forwarded.split(",")[0].strip()
    return direct_host


def _is_allowed(client_ip: str | None, allowed: tuple[str, ...]) -> bool:
    if client_ip is None:
        return False
    try:
        address = ipaddress.ip_address(client_ip)
    except ValueError:
        return False
    for entry in allowed:
        try:
            if "/" in entry:
                if address in ipaddress.ip_network(entry, strict=False):
                    return True
            elif address == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


class IPAllowlistMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path.startswith(_EXEMPT_PATHS):
            return await call_next(request)

        settings = get_network_agent_settings()
        allowed = tuple(settings.allowed_source_ips)

        if not allowed:
            # No allowlist configured. Tolerated outside production (initial
            # setup, local dev) but every request is logged so this never
            # goes unnoticed in a staging/production environment by accident.
            if settings.environment == "production":
                logger.warning(
                    "ip_allowlist.unconfigured_in_production",
                    path=request.url.path,
                )
            return await call_next(request)

        client_ip = _client_ip(request)
        if not _is_allowed(client_ip, allowed):
            logger.warning(
                "ip_allowlist.rejected", client_ip=client_ip, path=request.url.path
            )
            return JSONResponse(
                status_code=403, content={"detail": "Source IP not allowed"}
            )

        return await call_next(request)
