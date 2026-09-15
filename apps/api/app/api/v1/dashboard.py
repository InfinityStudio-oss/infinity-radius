"""Tenant dashboard landing page — thin route handlers, aggregation logic
in DashboardService. Every response is scoped to `ctx.tenant_id`, resolved
server-side from the verified session (see app.core.context) — a client
can never supply or influence which tenant's data comes back."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.roles import TENANT_STAFF_ROLES
from app.db.session import get_db
from app.schemas.dashboard import (
    CollectionsTrendPoint,
    DashboardSummaryRead,
    PackagePerformanceRow,
    SessionTrendPoint,
)
from app.schemas.envelope import ApiResponse
from app.services.dashboard import DashboardService

router = APIRouter()

require_dashboard_viewer = require_tenant_role(*TENANT_STAFF_ROLES)


@router.get("/summary", response_model=ApiResponse[DashboardSummaryRead])
async def get_dashboard_summary(
    ctx: TenantContext = Depends(require_dashboard_viewer),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[DashboardSummaryRead]:
    summary = await DashboardService(db).summary(tenant_id=ctx.tenant_id)
    return ApiResponse(
        data=DashboardSummaryRead(
            online_users=summary.online_users,
            today_collections_tzs=summary.today_collections_tzs,
            active_vouchers=summary.active_vouchers,
            routers_online=summary.routers_online,
            routers_total=summary.routers_total,
            failed_transactions=summary.failed_transactions,
            available_wallet_balance_tzs=summary.available_wallet_balance_tzs,
        )
    )


@router.get("/collections-trend", response_model=ApiResponse[list[CollectionsTrendPoint]])
async def get_collections_trend(
    ctx: TenantContext = Depends(require_dashboard_viewer),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[CollectionsTrendPoint]]:
    points = await DashboardService(db).collections_trend(tenant_id=ctx.tenant_id)
    return ApiResponse(data=points)


@router.get("/session-trend", response_model=ApiResponse[list[SessionTrendPoint]])
async def get_session_trend(
    ctx: TenantContext = Depends(require_dashboard_viewer),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[SessionTrendPoint]]:
    points = await DashboardService(db).session_trend(tenant_id=ctx.tenant_id)
    return ApiResponse(data=points)


@router.get("/package-performance", response_model=ApiResponse[list[PackagePerformanceRow]])
async def get_package_performance(
    ctx: TenantContext = Depends(require_dashboard_viewer),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[list[PackagePerformanceRow]]:
    rows = await DashboardService(db).package_performance(tenant_id=ctx.tenant_id)
    return ApiResponse(data=rows)
