"""Hotspot site locations — thin route handlers, logic in LocationService."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import NETWORK_ROLES, TENANT_STAFF_ROLES
from app.db.session import get_db
from app.schemas.envelope import ApiListResponse, ApiResponse
from app.schemas.locations import LocationCreate, LocationRead
from app.services.locations import LocationService

router = APIRouter()


@router.get("", response_model=ApiListResponse[LocationRead])
async def list_locations(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[LocationRead]:
    service = LocationService(db)
    items, total = await service.list(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[LocationRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.get("/{location_id}", response_model=ApiResponse[LocationRead])
async def get_location(
    location_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LocationRead]:
    service = LocationService(db)
    location = await service.get(tenant_id=ctx.tenant_id, location_id=location_id)
    return ApiResponse(data=LocationRead.model_validate(location))


@router.post("", response_model=ApiResponse[LocationRead], status_code=201)
async def create_location(
    payload: LocationCreate,
    ctx: TenantContext = Depends(require_tenant_role(*NETWORK_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[LocationRead]:
    service = LocationService(db)
    location = await service.create(
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        name=payload.name,
        region=payload.region,
        city=payload.city,
        address=payload.address,
    )
    await db.commit()
    return ApiResponse(data=LocationRead.model_validate(location))
