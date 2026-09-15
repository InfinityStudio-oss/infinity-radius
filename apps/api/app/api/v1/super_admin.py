"""Super-admin (platform operator) API surface for the super-admin shell.

`/overview`, `/resources/{resource}`, and `/system-health` below are an
earlier-phase surface — same honesty contract as app.api.v1.tenant, kept
exactly as-is (including their exact response shape, which
tests/test_super_admin.py locks in) since some frontend calls still hit
them. The routes further down (`/dashboard-summary` and friends) are the
real, backend-bound super-admin dashboard, mirroring
app/api/v1/dashboard.py's tenant-scoped equivalent but aggregated across
every tenant instead of one.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import Role
from app.core.security import AuthenticatedUser, require_role
from app.db.session import get_db
from app.schemas.audit import AuditLogRead
from app.schemas.common import MetricValue, ResourceListResponse
from app.schemas.dashboard import CollectionsTrendPoint
from app.schemas.envelope import ApiListResponse, ApiResponse
from app.schemas.super_admin_dashboard import (
    PendingPayoutRow,
    SuperAdminSummaryRead,
    TenantGrowthPoint,
)
from app.services.audit import AuditService
from app.services.super_admin_dashboard import SuperAdminDashboardService

router = APIRouter()

require_super_admin = require_role(Role.SUPER_ADMIN)

# Every list-type leaf under the super-admin sidebar.
SUPER_ADMIN_RESOURCES = frozenset(
    {
        "tenants",
        "tenant-plans",
        "hotspot-sites",
        "routers",
        "radius-servers",
        "network-agents",
        "system-logs",
        "collections",
        "wallets",
        "disbursements",
        "reconciliation",
        "support-tickets",
        "audit-logs",
    },
)


@router.get("/overview")
async def get_overview(
    user: AuthenticatedUser = Depends(require_super_admin),
) -> dict[str, MetricValue]:
    return {
        "tenants_total": MetricValue.not_configured(),
        "active_subscriptions": MetricValue.not_configured(),
        "platform_fee_mtd": MetricValue.not_configured(),
        "routers_online": MetricValue.not_configured(),
        "radius_sessions": MetricValue.not_configured(),
        "pending_payouts": MetricValue.not_configured(),
    }


@router.get("/resources/{resource}", response_model=ResourceListResponse)
async def list_resource(
    resource: str, user: AuthenticatedUser = Depends(require_super_admin)
) -> ResourceListResponse:
    if resource not in SUPER_ADMIN_RESOURCES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown resource '{resource}'",
        )

    return ResourceListResponse(items=[], total=0, status="not_configured")


@router.get("/system-health")
async def get_system_health(
    user: AuthenticatedUser = Depends(require_super_admin),
) -> dict[str, MetricValue]:
    return {
        "radius_cluster": MetricValue.not_configured(),
        "network_agents": MetricValue.not_configured(),
        "database": MetricValue.not_configured(),
        "payment_gateway": MetricValue.not_configured(),
    }


# --- Real, backend-bound platform dashboard -------------------------------


@router.get("/dashboard-summary", response_model=ApiResponse[SuperAdminSummaryRead])
async def get_dashboard_summary(
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[SuperAdminSummaryRead]:
    summary = await SuperAdminDashboardService(db).summary()
    return ApiResponse(
        data=SuperAdminSummaryRead(
            active_tenants=summary.active_tenants,
            suspended_tenants=summary.suspended_tenants,
            routers_total=summary.routers_total,
            routers_online=summary.routers_online,
            radius_active_sessions=summary.radius_active_sessions,
            collections_today_tzs=summary.collections_today_tzs,
            pending_payouts=summary.pending_payouts,
            pending_payouts_amount_tzs=summary.pending_payouts_amount_tzs,
            failed_webhooks=summary.failed_webhooks,
            # No reconciliation-exception table exists yet anywhere in this
            # schema — see app/services/super_admin_dashboard.py's module
            # docstring. Never a fabricated 0.
            reconciliation_exceptions=MetricValue.not_configured(),
        )
    )


@router.get("/collections-trend", response_model=ApiResponse[list[CollectionsTrendPoint]])
async def get_platform_collections_trend(
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[CollectionsTrendPoint]]:
    points = await SuperAdminDashboardService(db).collections_trend()
    return ApiResponse(data=points)


@router.get("/tenant-growth-trend", response_model=ApiResponse[list[TenantGrowthPoint]])
async def get_tenant_growth_trend(
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[TenantGrowthPoint]]:
    points = await SuperAdminDashboardService(db).tenant_growth_trend()
    return ApiResponse(data=points)


@router.get("/pending-payouts", response_model=ApiResponse[list[PendingPayoutRow]])
async def get_pending_payouts_queue(
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[PendingPayoutRow]]:
    rows = await SuperAdminDashboardService(db).pending_payouts_queue()
    return ApiResponse(data=rows)


@router.get("/audit-logs", response_model=ApiListResponse[AuditLogRead])
async def list_platform_audit_logs(
    params: ListParams = Depends(list_params),
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[AuditLogRead]:
    """Platform-wide audit trail — every tenant's events, not just one.
    tenant_id=None means "no tenant filter" (see BaseRepository), the same
    convention TenantService.list_all uses for the super-admin tenants list."""
    service = AuditService(db)
    items, total = await service.list(tenant_id=None, params=params)
    return ApiListResponse(
        data=[AuditLogRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )
