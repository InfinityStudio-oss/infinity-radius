"""Customer payment transactions — read-only, thin route handlers.

Populated once app.integrations.selcom's Collection API is implemented;
until then this legitimately (not fabricated) returns an empty list."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import FRONTLINE_ROLES
from app.db.session import get_db
from app.schemas.envelope import ApiListResponse, ApiResponse
from app.schemas.finance import TransactionRead
from app.services.payments import PaymentService

router = APIRouter()


@router.get("", response_model=ApiListResponse[TransactionRead])
async def list_payments(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*FRONTLINE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[TransactionRead]:
    service = PaymentService(db)
    items, total = await service.list(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[TransactionRead.from_transaction(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.get("/{transaction_id}", response_model=ApiResponse[TransactionRead])
async def get_payment(
    transaction_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*FRONTLINE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TransactionRead]:
    service = PaymentService(db)
    transaction = await service.get(tenant_id=ctx.tenant_id, transaction_id=transaction_id)
    return ApiResponse(data=TransactionRead.from_transaction(transaction))
