"""Super Admin ops diagnostics. SUPER_ADMIN only.

- Network Agent connectivity probe: verifies the real authenticated
  Railway -> Network Agent path end to end (deployed backend, real static
  outbound IP, real HMAC signature) without touching a real router.
- Selcom Business connectivity probe: verifies the real RSA-signed Railway
  -> Selcom Business path end to end (real static outbound IP, real
  signature, real IP whitelist) using only Selcom's own published sandbox
  test accounts — never a real destination, never real money.

Both use the existing signed clients — never a second signing implementation.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.roles import Role
from app.core.security import AuthenticatedUser, require_role
from app.integrations.network_agent.client import (
    NetworkAgentClient,
    NetworkAgentNotConfiguredError,
)
from app.integrations.selcom_business.client import SelcomBusinessClient
from app.integrations.selcom_business.config import selcom_business_config_from_settings
from app.integrations.selcom_business.errors import SelcomBusinessError
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


class SelcomBusinessDiagnosticResult(BaseModel):
    configured: bool
    environment: str | None = None
    reachable: bool
    resultcode: str | None = None
    message: str | None = None
    detail: str | None = None


# Selcom's own published sandbox test account ("Sandbox Selcom to Selcom",
# Internal Transfer) — see the "Sample Test Accounts" panel in the Selcom
# Business sandbox portal. Never a real destination; this is the one
# Selcom itself documents for exactly this kind of connectivity check.
_SANDBOX_TEST_BANK = "SELCOM"
_SANDBOX_TEST_ACCOUNT = "8774738353235"


@router.post(
    "/selcom-business", response_model=ApiResponse[SelcomBusinessDiagnosticResult]
)
async def diagnose_selcom_business(
    user: AuthenticatedUser = Depends(require_super_admin),
) -> ApiResponse[SelcomBusinessDiagnosticResult]:
    config = selcom_business_config_from_settings()
    if not config.is_configured:
        return ApiResponse(
            data=SelcomBusinessDiagnosticResult(
                configured=False,
                environment=config.environment,
                reachable=False,
                detail="SELCOM_BUSINESS_BASE_URL/API_KEY/PRIVATE_KEY_B64 not configured",
            )
        )

    client = SelcomBusinessClient(config)
    try:
        response = await client.account_lookup(
            bank=_SANDBOX_TEST_BANK,
            account=_SANDBOX_TEST_ACCOUNT,
            trans_id=f"diag-{user.id.hex}",
        )
    except SelcomBusinessError as exc:
        return ApiResponse(
            data=SelcomBusinessDiagnosticResult(
                configured=True,
                environment=config.environment,
                reachable=False,
                detail=str(exc),
            )
        )

    return ApiResponse(
        data=SelcomBusinessDiagnosticResult(
            configured=True,
            environment=config.environment,
            reachable=True,
            resultcode=response.resultcode,
            message=response.message,
        )
    )
