"""Customer subscriptions — thin route handlers, logic in SubscriptionService."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import FRONTLINE_ROLES, TENANT_STAFF_ROLES
from app.db.session import get_db
from app.schemas.billing import SubscriptionCreate, SubscriptionRead
from app.schemas.envelope import ApiListResponse, ApiResponse
from app.services.subscriptions import SubscriptionService

router = APIRouter()


@router.get("", response_model=ApiListResponse[SubscriptionRead])
async def list_subscriptions(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[SubscriptionRead]:
    service = SubscriptionService(db)
    items, total = await service.list(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[SubscriptionRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.get("/{subscription_id}", response_model=ApiResponse[SubscriptionRead])
async def get_subscription(
    subscription_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[SubscriptionRead]:
    service = SubscriptionService(db)
    subscription = await service.get(tenant_id=ctx.tenant_id, subscription_id=subscription_id)
    return ApiResponse(data=SubscriptionRead.model_validate(subscription))


@router.post("", response_model=ApiResponse[SubscriptionRead], status_code=201)
async def create_subscription(
    payload: SubscriptionCreate,
    ctx: TenantContext = Depends(require_tenant_role(*FRONTLINE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[SubscriptionRead]:
    service = SubscriptionService(db)
    subscription = await service.create(
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        customer_id=payload.customer_id,
        package_id=payload.package_id,
    )
    await db.commit()
    return ApiResponse(data=SubscriptionRead.model_validate(subscription))


@router.post("/{subscription_id}/activate", response_model=ApiResponse[SubscriptionRead])
async def activate_subscription(
    subscription_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*FRONTLINE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[SubscriptionRead]:
    """Manually activates a PENDING subscription — e.g. a first_use package
    whose activation isn't triggered by a voucher redemption."""
    service = SubscriptionService(db)
    subscription = await service.activate(
        tenant_id=ctx.tenant_id, actor_id=ctx.user.id, subscription_id=subscription_id
    )
    await db.commit()
    return ApiResponse(data=SubscriptionRead.model_validate(subscription))
