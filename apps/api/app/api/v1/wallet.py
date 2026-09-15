"""Tenant wallet + ledger — thin route handlers, logic in WalletService."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import FINANCE_ROLES
from app.db.session import get_db
from app.schemas.envelope import ApiListResponse, ApiResponse
from app.schemas.finance import LedgerEntryRead, WalletRead
from app.services.wallet import WalletService

router = APIRouter()


@router.get("", response_model=ApiResponse[WalletRead])
async def get_wallet(
    ctx: TenantContext = Depends(require_tenant_role(*FINANCE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[WalletRead]:
    service = WalletService(db)
    wallet = await service.get_or_create_wallet(tenant_id=ctx.tenant_id)
    await db.commit()
    return ApiResponse(data=WalletRead.model_validate(wallet))


@router.get("/ledger", response_model=ApiListResponse[LedgerEntryRead])
async def list_ledger(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*FINANCE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[LedgerEntryRead]:
    service = WalletService(db)
    items, total = await service.list_ledger(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[LedgerEntryRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )
