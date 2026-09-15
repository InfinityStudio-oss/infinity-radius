"""Connectivity sessions — read-only, thin route handlers, logic in SessionService."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import TENANT_STAFF_ROLES
from app.db.session import get_db
from app.schemas.envelope import ApiListResponse, ApiResponse
from app.schemas.sessions import SessionRead
from app.services.sessions import SessionService

router = APIRouter()


@router.get("", response_model=ApiListResponse[SessionRead])
async def list_sessions(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[SessionRead]:
    service = SessionService(db)
    items, total = await service.list(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[SessionRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )


@router.get("/{session_id}", response_model=ApiResponse[SessionRead])
async def get_session(
    session_id: UUID,
    ctx: TenantContext = Depends(require_tenant_role(*TENANT_STAFF_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[SessionRead]:
    service = SessionService(db)
    session = await service.get(tenant_id=ctx.tenant_id, session_id=session_id)
    return ApiResponse(data=SessionRead.model_validate(session))
