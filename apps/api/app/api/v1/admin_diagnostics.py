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
from app.integrations.selcom_business.schemas import money_from_provider
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

    # Environment-aware safety: _SANDBOX_TEST_ACCOUNT is Selcom's own
    # published SANDBOX sample account — there is no documented safe
    # production equivalent, so this diagnostic must never fire it against
    # a production base URL. Never a disbursement either way (account
    # lookup only), but sending a known-fake test account to a live
    # production endpoint is exactly the "invented behavior" this platform
    # avoids — refuse closed instead of guessing.
    if config.environment != "sandbox":
        return ApiResponse(
            data=SelcomBusinessDiagnosticResult(
                configured=True,
                environment=config.environment,
                reachable=False,
                detail="This diagnostic only ever runs against sandbox — "
                "SELCOM_BUSINESS_ENVIRONMENT is not 'sandbox', so no request was sent. "
                "No documented safe production connectivity check exists yet; see "
                "docs/architecture.md's production activation runbook.",
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


class SelcomProviderBalanceResult(BaseModel):
    """"Selcom Provider Balance" — the platform's own Selcom Business
    operating account, never a tenant's wallet balance (see
    app/services/wallet.py for that, an entirely separate concept). Only
    ever visible to SUPER_ADMIN, never surfaced to any tenant route."""

    configured: bool
    environment: str | None = None
    available_balance: str | None = None
    currency: str | None = None
    masked_account_number: str | None = None
    detail: str | None = None


def _mask_account_number(account_number: str | None) -> str | None:
    if not account_number:
        return None
    if len(account_number) <= 4:
        return "*" * len(account_number)
    return "*" * (len(account_number) - 4) + account_number[-4:]


@router.post(
    "/selcom-business/provider-balance", response_model=ApiResponse[SelcomProviderBalanceResult]
)
async def selcom_provider_balance(
    user: AuthenticatedUser = Depends(require_super_admin),
) -> ApiResponse[SelcomProviderBalanceResult]:
    """Read-only — the ONE Selcom Business endpoint that reports the
    platform's own operating balance, not any customer/tenant balance.
    SUPER_ADMIN-only (no tenant route ever calls this); never invented —
    only exposes what developer.selcom.business's own Balance endpoint
    returns."""
    config = selcom_business_config_from_settings()
    if not config.is_configured or not config.account_number:
        return ApiResponse(
            data=SelcomProviderBalanceResult(
                configured=False,
                environment=config.environment,
                detail="SELCOM_BUSINESS_BASE_URL/API_KEY/PRIVATE_KEY_B64/ACCOUNT_NUMBER "
                "not fully configured",
            )
        )

    # Unlike diagnose_selcom_business above, this is safe in EITHER
    # environment: it always queries whichever account_number is actually
    # configured (sandbox's own test account when environment=sandbox,
    # the real production account when environment=production) — there is
    # no hardcoded/fake account that could be misdirected at the wrong
    # environment. Read-only, no money movement either way. This is the
    # intended non-money-moving production connectivity check (see
    # docs/architecture.md's production activation runbook).
    client = SelcomBusinessClient(config)
    try:
        response = await client.balance(account_number=config.account_number)
    except SelcomBusinessError as exc:
        return ApiResponse(
            data=SelcomProviderBalanceResult(
                configured=True, environment=config.environment, detail=str(exc)
            )
        )

    data = response.data
    balance_value = money_from_provider(data.available_balance) if data else None
    return ApiResponse(
        data=SelcomProviderBalanceResult(
            configured=True,
            environment=config.environment,
            available_balance=str(balance_value) if balance_value is not None else None,
            currency=data.currency if data else None,
            masked_account_number=_mask_account_number(config.account_number),
        )
    )
