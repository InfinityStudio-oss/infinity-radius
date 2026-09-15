"""Tenant reports — thin route handlers, logic in ReportService."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.roles import FINANCE_ROLES
from app.db.session import get_db
from app.schemas.envelope import ApiResponse
from app.schemas.reports import TenantSummaryRead
from app.services.reports import ReportService

router = APIRouter()


@router.get("/summary", response_model=ApiResponse[TenantSummaryRead])
async def get_tenant_summary(
    ctx: TenantContext = Depends(require_tenant_role(*FINANCE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantSummaryRead]:
    service = ReportService(db)
    summary = await service.tenant_summary(tenant_id=ctx.tenant_id)
    return ApiResponse(
        data=TenantSummaryRead(
            customers_total=summary.customers_total,
            routers_total=summary.routers_total,
            routers_online=summary.routers_online,
            active_subscriptions=summary.active_subscriptions,
            transactions_total=summary.transactions_total,
            wallet_balance=summary.wallet_balance,
        )
    )
