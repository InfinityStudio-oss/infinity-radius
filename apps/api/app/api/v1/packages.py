"""WiFi access packages — thin route handlers, logic in PackageService."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import MANAGEMENT_ROLES, TENANT_STAFF_ROLES
from app.db.session import get_db
from app.schemas.billing import PackageCreate, PackageRead
from app.schemas.envelope import ApiListResponse, ApiResponse
from app.services.packages import PackageService

router = APIRouter()


@router.get("", response_model=ApiListResponse[PackageRead])
async def list_packages(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[PackageRead]:
    service = PackageService(db)
    items, total = await service.list(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[PackageRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.get("/{package_id}", response_model=ApiResponse[PackageRead])
async def get_package(
    package_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PackageRead]:
    service = PackageService(db)
    package = await service.get(tenant_id=ctx.tenant_id, package_id=package_id)
    return ApiResponse(data=PackageRead.model_validate(package))


@router.post("", response_model=ApiResponse[PackageRead], status_code=201)
async def create_package(
    payload: PackageCreate,
    ctx: TenantContext = Depends(require_tenant_role(*MANAGEMENT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[PackageRead]:
    service = PackageService(db)
    package = await service.create(
        tenant_id=ctx.tenant_id,
        actor_id=ctx.user.id,
        name=payload.name,
        description=payload.description,
        price_tzs=payload.price_tzs,
        duration_minutes=payload.duration_minutes,
        bytes_limit=payload.bytes_limit,
        download_speed_kbps=payload.download_speed_kbps,
        upload_speed_kbps=payload.upload_speed_kbps,
        device_limit=payload.device_limit,
        simultaneous_sessions=payload.simultaneous_sessions,
        activation_type=payload.activation_type,
        status=payload.status,
    )
    await db.commit()
    return ApiResponse(data=PackageRead.model_validate(package))
