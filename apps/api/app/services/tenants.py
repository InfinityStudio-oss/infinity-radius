from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.pagination import ListParams
from app.models.tenancy import Tenant
from app.repositories.tenancy import TenantRepository


class TenantService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = TenantRepository(db)

    async def list_all(self, *, params: ListParams) -> tuple[list[Tenant], int]:
        """Platform-wide listing — super admin only; deliberately takes no
        tenant_id (there isn't one to scope by)."""
        return await self.repo.list_paginated(tenant_id=None, params=params)

    async def get(self, *, tenant_id: UUID) -> Tenant:
        tenant = await self.repo.get_by_id(tenant_id=None, id=tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found")
        return tenant
