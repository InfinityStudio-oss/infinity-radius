from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PackageActivationType, PackageStatus
from app.core.errors import NotFoundError
from app.core.pagination import ListParams
from app.models.network import Package
from app.repositories.billing import PackageRepository
from app.services.audit import write_audit_log


class PackageService:
    """WiFi access plans. Every package is created by the tenant themselves —
    nothing here is ever seeded as a default/sample offering."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = PackageRepository(db)

    async def list_active_packages(self, *, tenant_id: UUID) -> list[Package]:
        """For the public captive portal — only ever this tenant's own
        active packages, resolved from a signed router token, never a
        tenant_id taken directly from client input."""
        stmt = select(Package).where(
            Package.tenant_id == tenant_id, Package.status == PackageStatus.ACTIVE
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list(self, *, tenant_id: UUID, params: ListParams) -> tuple[list[Package], int]:
        return await self.repo.list_paginated(tenant_id=tenant_id, params=params)

    async def get(self, *, tenant_id: UUID, package_id: UUID) -> Package:
        package = await self.repo.get_by_id(tenant_id=tenant_id, id=package_id)
        if package is None:
            raise NotFoundError("Package not found")
        return package

    async def create(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        name: str,
        description: str | None,
        price_tzs: Decimal,
        duration_minutes: int | None,
        bytes_limit: int | None,
        download_speed_kbps: int | None,
        upload_speed_kbps: int | None,
        device_limit: int,
        simultaneous_sessions: int,
        activation_type: PackageActivationType,
        status: PackageStatus,
    ) -> Package:
        package = await self.repo.create(
            tenant_id=tenant_id,
            name=name,
            description=description,
            price_tzs=price_tzs,
            duration_minutes=duration_minutes,
            bytes_limit=bytes_limit,
            download_speed_kbps=download_speed_kbps,
            upload_speed_kbps=upload_speed_kbps,
            device_limit=device_limit,
            simultaneous_sessions=simultaneous_sessions,
            activation_type=str(activation_type),
            status=str(status),
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="package.created",
            target_type="package",
            target_id=package.id,
        )
        return package
