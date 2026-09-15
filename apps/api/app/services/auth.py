from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedUser
from app.repositories.tenancy import ProfileRepository, TenantRepository


@dataclass(frozen=True)
class CurrentUserView:
    id: UUID
    email: str | None
    full_name: str | None
    tenant_id: UUID | None
    tenant_name: str | None
    tenant_status: str | None
    roles: list[str]


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.profile_repo = ProfileRepository(db)
        self.tenant_repo = TenantRepository(db)

    async def get_current_user_view(self, user: AuthenticatedUser) -> CurrentUserView:
        profile = await self.profile_repo.get_by_id(tenant_id=None, id=user.id)

        tenant_name: str | None = None
        tenant_status: str | None = None
        if user.tenant_id is not None:
            tenant = await self.tenant_repo.get_by_id(tenant_id=None, id=user.tenant_id)
            if tenant is not None:
                tenant_name = tenant.name
                tenant_status = tenant.status

        return CurrentUserView(
            id=user.id,
            email=user.email,
            full_name=profile.full_name if profile is not None else None,
            tenant_id=user.tenant_id,
            tenant_name=tenant_name,
            tenant_status=tenant_status,
            roles=sorted(user.roles),
        )
