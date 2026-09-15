"""Auth — login/logout/password-reset all happen client-side against
Supabase Auth directly (see apps/web). This module exposes only what
needs the verified session: who the caller is, database-resolved."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.envelope import ApiResponse
from app.schemas.tenancy import CurrentUserRead
from app.services.auth import AuthService

router = APIRouter()


@router.get("/me", response_model=ApiResponse[CurrentUserRead])
async def get_me(
    user: AuthContext = Depends(get_auth_context),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse[CurrentUserRead]:
    service = AuthService(db)
    view = await service.get_current_user_view(user)
    return ApiResponse(
        data=CurrentUserRead(
            id=view.id,
            email=view.email,
            full_name=view.full_name,
            tenant_id=view.tenant_id,
            tenant_name=view.tenant_name,
            tenant_status=view.tenant_status,
            roles=view.roles,
        )
    )
