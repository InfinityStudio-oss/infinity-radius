"""Customers — thin route handlers only. All logic lives in CustomerService."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import FRONTLINE_ROLES, TENANT_STAFF_ROLES
from app.db.session import get_db
from app.schemas.customers import CustomerCreate, CustomerRead
from app.schemas.envelope import ApiListResponse, ApiResponse
from app.services.customers import CustomerService

router = APIRouter()


@router.get("", response_model=ApiListResponse[CustomerRead])
async def list_customers(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[CustomerRead]:
    service = CustomerService(db)
    items, total = await service.list(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[CustomerRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.get("/{customer_id}", response_model=ApiResponse[CustomerRead])
async def get_customer(
    customer_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CustomerRead]:
    service = CustomerService(db)
    customer = await service.get(tenant_id=ctx.tenant_id, customer_id=customer_id)
    return ApiResponse(data=CustomerRead.model_validate(customer))


@router.post("", response_model=ApiResponse[CustomerRead], status_code=201)
async def create_customer(
    payload: CustomerCreate,
    ctx: TenantContext = Depends(require_tenant_role(*FRONTLINE_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CustomerRead]:
    service = CustomerService(db)
    customer = await service.create(
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        first_name=payload.first_name,
        last_name=payload.last_name,
        phone=payload.phone,
        email=payload.email,
        username=payload.username,
        notes=payload.notes,
    )
    await db.commit()
    return ApiResponse(data=CustomerRead.model_validate(customer))
