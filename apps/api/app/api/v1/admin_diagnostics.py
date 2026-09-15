"""Super Admin ops diagnostics. SUPER_ADMIN only.

Currently just the Network Agent connectivity probe, added to verify the
real authenticated Railway -> Network Agent path end to end (deployed
backend, real static outbound IP, real HMAC signature) without touching a
real router. Uses the existing signed client (see
app.integrations.network_agent) — never a second signing implementation.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.roles import Role
from app.core.security import AuthenticatedUser, require_role
from app.integrations.network_agent.client import (
    NetworkAgentClient,
    NetworkAgentNotConfiguredError,
)
from app.schemas.envelope import ApiResponse

router = APIRouter()

require_super_admin = require_role(Role.SUPER_ADMIN)


class NetworkAgentDiagnosticResult(BaseModel):
    reachable: bool
    authenticated: bool
    status_code: int | None = None
    detail: str | None = None


@router.post("/network-agent", response_model=ApiResponse[NetworkAgentDiagnosticResult])
async def diagnose_network_agent(
    user: AuthenticatedUser = Depends(require_super_admin),
) -> ApiResponse[NetworkAgentDiagnosticResult]:
    try:
        async with NetworkAgentClient() as client:
            authenticated, status_code = await client.diagnostic_ping()
    except NetworkAgentNotConfiguredError:
        return ApiResponse(
            data=NetworkAgentDiagnosticResult(
                reachable=False,
                authenticated=False,
                detail="NETWORK_AGENT_BASE_URL/NETWORK_AGENT_API_KEY not configured",
            )
        )
    except Exception:  # noqa: BLE001 — network/TLS failure, never a secret
        return ApiResponse(
            data=NetworkAgentDiagnosticResult(
                reachable=False,
                authenticated=False,
                detail="Network Agent unreachable",
            )
        )

    return ApiResponse(
        data=NetworkAgentDiagnosticResult(
            reachable=True,
            authenticated=authenticated,
            status_code=status_code,
        )
    )
