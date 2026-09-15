from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.pagination import ListParams
from app.models.network import Location
from app.repositories.network import LocationRepository
from app.services.audit import write_audit_log


class LocationService:
    """Hotspot sites. Region/city are whatever the tenant supplies — never
    a hard-coded city — anywhere within their country (Tanzania by default)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = LocationRepository(db)

    async def list(self, *, tenant_id: UUID, params: ListParams) -> tuple[list[Location], int]:
        return await self.repo.list_paginated(tenant_id=tenant_id, params=params)

    async def get(self, *, tenant_id: UUID, location_id: UUID) -> Location:
        location = await self.repo.get_by_id(tenant_id=tenant_id, id=location_id)
        if location is None:
            raise NotFoundError("Location not found")
        return location

    async def create(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        name: str,
        region: str | None,
        city: str | None,
        address: str | None,
    ) -> Location:
        location = await self.repo.create(
            tenant_id=tenant_id, name=name, region=region, city=city, address=address
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="location.created",
            target_type="location",
            target_id=location.id,
        )
        return location
