"""Offline vouchers — thin route handlers, logic in VoucherService."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import FRONTLINE_ROLES, TENANT_STAFF_ROLES
from app.db.session import get_db
from app.schemas.billing import SubscriptionRead
from app.schemas.envelope import ApiListResponse, ApiResponse
from app.schemas.vouchers import (
    OfflineVoucherRead,
    VoucherBatchCreate,
    VoucherBatchRead,
    VoucherRedeemRequest,
    VoucherRedeemResult,
)
from app.services.vouchers import VoucherService

router = APIRouter()


@router.get("/batches", response_model=ApiListResponse[VoucherBatchRead])
async def list_voucher_batches(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[VoucherBatchRead]:
    service = VoucherService(db)
    items, total = await service.list_batches(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[VoucherBatchRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.get("/batches/{batch_id}", response_model=ApiResponse[VoucherBatchRead])
async def get_voucher_batch(
    batch_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[VoucherBatchRead]:
    service = VoucherService(db)
    batch = await service.get_batch(tenant_id=ctx.tenant_id, batch_id=batch_id)
    return ApiResponse(data=VoucherBatchRead.model_validate(batch))


@router.post("/batches", response_model=ApiResponse[VoucherBatchRead], status_code=201)
async def generate_voucher_batch(
    payload: VoucherBatchCreate,
    ctx: TenantContext = Depends(require_tenant_role(*FRONTLINE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[VoucherBatchRead]:
    service = VoucherService(db)
    batch = await service.generate_batch(
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        package_id=payload.package_id,
        quantity=payload.quantity,
        prefix=payload.prefix,
    )
    await db.commit()
    return ApiResponse(data=VoucherBatchRead.model_validate(batch))


@router.get("/codes", response_model=ApiListResponse[OfflineVoucherRead])
async def list_voucher_codes(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[OfflineVoucherRead]:
    service = VoucherService(db)
    items, total = await service.list_vouchers(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[OfflineVoucherRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.post("/redeem", response_model=ApiResponse[VoucherRedeemResult])
async def redeem_voucher(
    payload: VoucherRedeemRequest,
    ctx: TenantContext = Depends(require_tenant_role(*FRONTLINE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[VoucherRedeemResult]:
    service = VoucherService(db)
    voucher, subscription = await service.redeem(
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        code=payload.code,
        customer_id=payload.customer_id,
    )
    await db.commit()
    return ApiResponse(
        data=VoucherRedeemResult(
            voucher=OfflineVoucherRead.model_validate(voucher),
            subscription=SubscriptionRead.model_validate(subscription),
        )
    )
