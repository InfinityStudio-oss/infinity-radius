"""Tenant-scoped API surface for the dashboard shell.

Every route here is intentionally honest about the current build phase: the
billing/RADIUS/router schema does not exist yet, so list resources report
`not_configured` with empty `items` rather than querying tables that don't
exist, and overview metrics report `not_configured` rather than a fabricated
number. Once the corresponding schema/integration lands, only the query
logic in these handlers needs to change — response shape and RBAC stay put.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.roles import TENANT_STAFF_ROLES
from app.core.security import AuthenticatedUser, require_role
from app.schemas.common import MetricValue, ResourceListResponse

router = APIRouter()

require_tenant_user = require_role(*TENANT_STAFF_ROLES)

# Every list-type leaf under the tenant dashboard sidebar.
TENANT_RESOURCES = frozenset(
    {
        "customers",
        "online-users",
        "hotspot-sites",
        "routers",
        "radius-users",
        "sessions",
        "packages",
        "subscriptions",
        "vouchers",
        "payments",
        "wallet-transactions",
        "payouts",
        "settlement-logs",
        "ledger",
        "reconciliation",
        "reports",
        "staff",
        "support-tickets",
    },
)


@router.get("/overview")
async def get_overview(
    user: AuthenticatedUser = Depends(require_tenant_user),
) -> dict[str, MetricValue]:
    # No customer/router/session/billing schema exists yet — every metric is
    # honestly "not_configured" until the relevant tables/integrations land.
    return {
        "customers_total": MetricValue.not_configured(),
        "online_users": MetricValue.not_configured(),
        "routers_online": MetricValue.not_configured(),
        "active_sessions": MetricValue.not_configured(),
        "revenue_today": MetricValue.not_configured(),
        "active_vouchers": MetricValue.not_configured(),
    }


@router.get("/resources/{resource}", response_model=ResourceListResponse)
async def list_resource(
    resource: str,
    user: AuthenticatedUser = Depends(require_tenant_user),
) -> ResourceListResponse:
    if resource not in TENANT_RESOURCES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown resource '{resource}'",
        )

    return ResourceListResponse(items=[], total=0, status="not_configured")
