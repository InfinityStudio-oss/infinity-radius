from fastapi import FastAPI

from app.core.ip_allowlist import IPAllowlistMiddleware
from app.routers.health import router as health_router
from app.routers.mikrotik import router as mikrotik_router

app = FastAPI(
    title="Infinity Radius Network Agent",
    description=(
        "Bridges the FastAPI backend to MikroTik routers over WireGuard. "
        "Deployed on the Network VPS, never on Railway."
    ),
    version="0.1.0",
)

# Outermost: every request except /health must come from an allowed source
# IP (Railway's static outbound IPs) before it's even considered — see
# app.core.ip_allowlist. Defense in depth alongside, never instead of, the
# per-route request signature check (app.core.security.verify_agent_signature).
app.add_middleware(IPAllowlistMiddleware)

# /health is intentionally unauthenticated and IP-allowlist-exempt (used by
# uptime monitoring on the VPS itself, reachable only via Caddy's reverse
# proxy — see infrastructure/caddy/Caddyfile).
app.include_router(health_router)

# Every route here depends on verify_agent_signature and takes only a
# router UUID — see app/routers/mikrotik.py.
app.include_router(mikrotik_router)
