"""Super Admin tenant review workflow — approve/reject/request-more-info/
suspend/reactivate, plus the queue/detail reads the review UI needs.
SUPER_ADMIN only, distinct from the existing /tenants router (which
predates onboarding and serves other super-admin tenant actions like
commercial terms and wallet adjustments).
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.roles import Role
from app.core.security import AuthenticatedUser, require_role
from app.db.session import get_db
from app.schemas.envelope import ApiListResponse, ApiResponse, PaginationMeta
from app.schemas.onboarding import (
    AdminRejectTenantRequest,
    AdminRequestMoreInformationRequest,
    AdminSetFeatureFlagRequest,
    AdminSuspendTenantRequest,
    AdminTenantDetailRead,
    AdminTenantQueueRow,
    TenantFeatureFlagsRead,
)
from app.schemas.tenancy import TenantRead
from app.services.admin_tenants import AdminTenantService

router = APIRouter()

require_super_admin = require_role(Role.SUPER_ADMIN)


@router.get("", response_model=ApiListResponse[AdminTenantQueueRow])
async def list_tenant_queue(
    status: str | None = None,
    _: object = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[AdminTenantQueueRow]:
    rows = await AdminTenantService(db).list_queue(status_filter=status)
    return ApiListResponse(
        data=rows,
        meta=PaginationMeta(
            page=1, page_size=max(len(rows), 1), total=len(rows), total_pages=1 if rows else 0
        ),
    )


@router.get("/{tenant_id}", response_model=ApiResponse[AdminTenantDetailRead])
async def get_tenant_detail(
    tenant_id: UUID,
    _: object = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[AdminTenantDetailRead]:
    detail = await AdminTenantService(db).get_detail(tenant_id=tenant_id)
    return ApiResponse(data=detail)


@router.post("/{tenant_id}/approve", response_model=ApiResponse[TenantRead])
async def approve_tenant(
    tenant_id: UUID,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantRead]:
    tenant = await AdminTenantService(db).approve(tenant_id=tenant_id, actor_id=user.id)
    return ApiResponse(data=TenantRead.model_validate(tenant))


@router.post("/{tenant_id}/reject", response_model=ApiResponse[TenantRead])
async def reject_tenant(
    tenant_id: UUID,
    payload: AdminRejectTenantRequest,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantRead]:
    tenant = await AdminTenantService(db).reject(
        tenant_id=tenant_id, actor_id=user.id, reason=payload.reason
    )
    return ApiResponse(data=TenantRead.model_validate(tenant))


@router.post("/{tenant_id}/request-more-information", response_model=ApiResponse[TenantRead])
async def request_more_information(
    tenant_id: UUID,
    payload: AdminRequestMoreInformationRequest,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantRead]:
    tenant = await AdminTenantService(db).request_more_information(
        tenant_id=tenant_id, actor_id=user.id, message=payload.message
    )
    return ApiResponse(data=TenantRead.model_validate(tenant))


@router.post("/{tenant_id}/suspend", response_model=ApiResponse[TenantRead])
async def suspend_tenant(
    tenant_id: UUID,
    payload: AdminSuspendTenantRequest,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantRead]:
    tenant = await AdminTenantService(db).suspend(
        tenant_id=tenant_id, actor_id=user.id, reason=payload.reason
    )
    return ApiResponse(data=TenantRead.model_validate(tenant))


@router.post("/{tenant_id}/reactivate", response_model=ApiResponse[TenantRead])
async def reactivate_tenant(
    tenant_id: UUID,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantRead]:
    tenant = await AdminTenantService(db).reactivate(tenant_id=tenant_id, actor_id=user.id)
    return ApiResponse(data=TenantRead.model_validate(tenant))


@router.post("/{tenant_id}/collection", response_model=ApiResponse[TenantFeatureFlagsRead])
async def set_collection_enabled(
    tenant_id: UUID,
    payload: AdminSetFeatureFlagRequest,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantFeatureFlagsRead]:
    """Independent of approval — see app/services/admin_tenants.py's
    module-level policy note. Never edits a wallet balance."""
    flags = await AdminTenantService(db).set_collection_enabled(
        tenant_id=tenant_id, actor_id=user.id, enabled=payload.enabled
    )
    return ApiResponse(data=TenantFeatureFlagsRead.model_validate(flags))


@router.post("/{tenant_id}/payout", response_model=ApiResponse[TenantFeatureFlagsRead])
async def set_payout_enabled(
    tenant_id: UUID,
    payload: AdminSetFeatureFlagRequest,
    user: AuthenticatedUser = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[TenantFeatureFlagsRead]:
    """Independent of approval — see app/services/admin_tenants.py's
    module-level policy note. Never edits a wallet balance or approves/
    rejects an individual withdrawal."""
    flags = await AdminTenantService(db).set_payout_enabled(
        tenant_id=tenant_id, actor_id=user.id, enabled=payload.enabled
    )
    return ApiResponse(data=TenantFeatureFlagsRead.model_validate(flags))
