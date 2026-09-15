"""Audit trail — read-only, thin route handlers. Append-only writes happen
inside other services via app.services.audit.write_audit_log; there is no
client-facing write endpoint here by design."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import TenantContext, require_tenant_role
from app.core.pagination import ListParams, build_pagination_meta, list_params
from app.core.roles import MANAGEMENT_ROLES
from app.db.session import get_db
from app.schemas.audit import AuditLogRead
from app.schemas.envelope import ApiListResponse
from app.services.audit import AuditService

router = APIRouter()


@router.get("", response_model=ApiListResponse[AuditLogRead])
async def list_audit_logs(
    params: ListParams = Depends(list_params),
    ctx: TenantContext = Depends(require_tenant_role(*MANAGEMENT_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> ApiListResponse[AuditLogRead]:
    service = AuditService(db)
    items, total = await service.list(tenant_id=ctx.tenant_id, params=params)
    return ApiListResponse(
        data=[AuditLogRead.model_validate(item) for item in items],
        meta=build_pagination_meta(total=total, params=params),
    )
