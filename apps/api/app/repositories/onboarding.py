from uuid import UUID

from sqlalchemy import select

from app.models.onboarding import EmailEvent, TenantFeatureFlags, TenantSettings, TenantVerification
from app.repositories.base import BaseRepository


class TenantSettingsRepository(BaseRepository[TenantSettings]):
    model = TenantSettings


class TenantFeatureFlagsRepository(BaseRepository[TenantFeatureFlags]):
    model = TenantFeatureFlags

    async def get_by_tenant(self, *, tenant_id: UUID) -> TenantFeatureFlags | None:
        stmt = select(TenantFeatureFlags).where(TenantFeatureFlags.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()


class TenantVerificationRepository(BaseRepository[TenantVerification]):
    model = TenantVerification

    async def get_by_tenant(self, *, tenant_id: UUID) -> TenantVerification | None:
        stmt = select(TenantVerification).where(TenantVerification.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()


class EmailEventRepository(BaseRepository[EmailEvent]):
    model = EmailEvent
