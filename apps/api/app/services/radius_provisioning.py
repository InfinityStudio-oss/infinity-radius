"""Chooses HOW a customer's RADIUS access gets provisioned, and is the
only place that decision is made.

Two transports exist, in strict preference order:

  1. NETWORK AGENT (production). Railway asks the agent on the Network VPS
     to write the rows; the agent talks to FreeRADIUS's PostgreSQL over
     localhost. The database is never reachable from the internet. This is
     the same authenticated, IP-allowlisted, signature-verified channel
     already used for every other privileged VPS operation.

  2. DIRECT DATABASE (local development and the test suite). Used only
     when RADIUS_DATABASE_URL is set, which in this deployment means a
     local Postgres on the developer's own machine.

Production deliberately has RADIUS_DATABASE_URL UNSET. Exposing the VPS's
PostgreSQL publicly just to satisfy it would tear a hole through the
security model the agent exists to enforce — so transport 1 is the answer
there, not a relaxed transport 2.

If NEITHER transport is available, provisioning raises. It never silently
"succeeds": a paying customer with no internet must surface as an
activation failure that support can see and the retry sweep can fix, not
as a quiet no-op.
"""

from uuid import UUID

import structlog

from app.core.config import get_settings
from app.integrations.network_agent.client import (
    NetworkAgentClient,
    NetworkAgentError,
    NetworkAgentNotConfiguredError,
)
from app.services import radius_sync

logger = structlog.get_logger("services.radius_provisioning")


class RadiusUnavailableError(RuntimeError):
    """No provisioning transport is available, or the chosen one failed.

    Always recoverable by design: the caller records activation FAILED and
    the retry sweep tries again once the transport is back.
    """


def _direct_db_available() -> bool:
    return get_settings().radius_database_url is not None


def _agent_available() -> bool:
    settings = get_settings()
    return bool(settings.network_agent_base_url and settings.network_agent_api_key)


def describe_transport() -> str:
    """Which transport would be used right now — for health/diagnostics and
    for the readiness question 'can this deployment actually activate
    access?'."""
    if _agent_available():
        return "network_agent"
    if _direct_db_available():
        return "direct_database"
    return "unavailable"


async def provision_access(
    *,
    customer_phone: str,
    package_id: UUID,
    radius_password: str,
    download_speed_kbps: int | None,
    upload_speed_kbps: int | None,
    session_timeout_seconds: int | None,
    simultaneous_sessions: int,
) -> str:
    """Grants one customer access. Returns the transport used.

    Idempotent through both transports: every underlying operation is an
    upsert, so a retry converges rather than duplicating or erroring.
    """
    if _agent_available():
        try:
            async with NetworkAgentClient() as client:
                await client.sync_radius_package_group(
                    package_id=package_id,
                    download_speed_kbps=download_speed_kbps,
                    upload_speed_kbps=upload_speed_kbps,
                    session_timeout_seconds=session_timeout_seconds,
                    simultaneous_sessions=simultaneous_sessions,
                )
                await client.provision_radius_user(
                    username=customer_phone,
                    package_id=package_id,
                    password=radius_password,
                )
        except (NetworkAgentError, NetworkAgentNotConfiguredError) as exc:
            # Never fall through to the direct database on an agent
            # failure. In production that path is unconfigured anyway, and
            # silently trying a second transport would hide a real outage
            # that operators need to see.
            raise RadiusUnavailableError(
                f"Network Agent RADIUS provisioning failed: {exc}"
            ) from exc
        return "network_agent"

    if _direct_db_available():
        try:
            await radius_sync.sync_package_radius_group(
                package_id=package_id,
                download_speed_kbps=download_speed_kbps,
                upload_speed_kbps=upload_speed_kbps,
                session_timeout_seconds=session_timeout_seconds,
                simultaneous_sessions=simultaneous_sessions,
            )
            await radius_sync.provision_customer_radius_access(
                customer_phone=customer_phone,
                package_id=package_id,
                radius_password=radius_password,
            )
        except Exception as exc:  # noqa: BLE001 — any DB failure is recoverable
            raise RadiusUnavailableError(f"RADIUS provisioning failed: {exc}") from exc
        return "direct_database"

    raise RadiusUnavailableError(
        "No RADIUS provisioning transport is configured. Set "
        "NETWORK_AGENT_BASE_URL/NETWORK_AGENT_API_KEY (production) or "
        "RADIUS_DATABASE_URL (local development)."
    )
