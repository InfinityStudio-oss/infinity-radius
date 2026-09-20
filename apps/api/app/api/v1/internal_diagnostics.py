"""Internal service-to-service diagnostics — read-only reachability
checks that prove a dependency chain works without touching any data.

Exists because the RADIUS provisioning path spans three hops that no
single component can verify alone:

    Railway web --signed HMAC--> Network Agent --localhost--> RADIUS DB

The agent can prove its own database connection, and the backend can
prove it holds a Network Agent key, but only a real signed request from
Railway proves ALL of it: the base URL, the HMAC secret, the signature
scheme, Railway's outbound IP against the agent's allowlist, the route
itself, and the database behind it. Getting that verified before the
first paying customer is the difference between discovering a broken
activation path in a test and discovering it after taking someone's
money.

Guarded by the same INTERNAL_WORKER_WEB_HMAC_KEY scheme as the other
internal routes (see app/core/internal_auth.py) — never a tenant JWT,
never the Super Admin JWT, and never public. Strictly non-mutating: it
calls only GET /radius/ping, which runs `SELECT 1`. It cannot create a
customer, a package group, or touch a router.
"""

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.internal_auth import require_internal_auth
from app.integrations.network_agent.client import (
    NetworkAgentClient,
    NetworkAgentError,
    NetworkAgentNotConfiguredError,
)

logger = structlog.get_logger("api.internal_diagnostics")

router = APIRouter()


class RadiusPingResponse(BaseModel):
    """Deliberately minimal. No DSN, no credentials, no agent key, no
    host — a diagnostic must never become an information-disclosure
    endpoint, even behind authentication."""

    # Did the signed request reach the agent and come back 2xx? Proves
    # base URL + HMAC + signature + IP allowlist + route.
    agent_reachable: bool
    # Did the agent's own local RADIUS database answer? Proves the last hop.
    radius_reachable: bool
    detail: str | None = None


@router.post(
    "/diagnostics/radius-ping",
    response_model=RadiusPingResponse,
    dependencies=[Depends(require_internal_auth)],
)
async def radius_ping() -> RadiusPingResponse:
    try:
        async with NetworkAgentClient() as client:
            radius_reachable = await client.radius_ping()
    except NetworkAgentNotConfiguredError:
        return RadiusPingResponse(
            agent_reachable=False,
            radius_reachable=False,
            detail="NETWORK_AGENT_BASE_URL/NETWORK_AGENT_API_KEY not configured",
        )
    except NetworkAgentError as exc:
        # Covers a rejected signature, a blocked source IP, a missing
        # route and an unreachable host alike. The reason is logged for
        # operators but deliberately generalized in the response.
        logger.warning("internal_diagnostics.radius_ping_failed", error=str(exc))
        return RadiusPingResponse(
            agent_reachable=False,
            radius_reachable=False,
            detail="Network Agent request failed",
        )

    logger.info("internal_diagnostics.radius_ping", radius_reachable=radius_reachable)
    return RadiusPingResponse(agent_reachable=True, radius_reachable=radius_reachable)
