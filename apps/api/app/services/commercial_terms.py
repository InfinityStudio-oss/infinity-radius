"""Tenant-specific commercial terms — the platform commission rate. Never
hard-coded: every tenant must have its own configured, auditable rate
before a collection can be processed (see WalletService.process_collection,
which fails closed with DomainValidationError when none is active).
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import DomainValidationError
from app.models.finance import TenantCommercialTerms
from app.repositories.finance import TenantCommercialTermsRepository
from app.services.audit import write_audit_log


class CommercialTermsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = TenantCommercialTermsRepository(db)

    async def get_active(self, *, tenant_id: UUID) -> TenantCommercialTerms | None:
        return await self.repo.get_active_for_tenant(tenant_id=tenant_id)

    async def require_active(self, *, tenant_id: UUID) -> TenantCommercialTerms:
        terms = await self.get_active(tenant_id=tenant_id)
        if terms is None:
            raise DomainValidationError(
                "No active commercial terms are configured for this tenant — a "
                "platform commission rate must be set before collections can be processed."
            )
        return terms

    async def set_commission_rate(
        self,
        *,
        tenant_id: UUID,
        commission_rate_percent: Decimal,
        actor_id: UUID | None,
        notes: str | None = None,
    ) -> TenantCommercialTerms:
        """Versions the tenant's commission rate: the current active row (if
        any) is deactivated and a new one inserted — rate history is never
        overwritten, only superseded."""
        if commission_rate_percent < 0 or commission_rate_percent > 100:
            raise DomainValidationError("commission_rate_percent must be between 0 and 100")

        current = await self.get_active(tenant_id=tenant_id)
        if current is not None:
            await self.repo.update(current, is_active=False)

        created = await self.repo.create(
            tenant_id=tenant_id,
            commission_rate_percent=str(commission_rate_percent),
            is_active=True,
            notes=notes,
            created_by=actor_id,
        )

        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="commercial_terms.rate_changed",
            target_type="tenant_commercial_terms",
            target_id=created.id,
            metadata={
                "commission_rate_percent": str(commission_rate_percent),
                "previous_rate_percent": (
                    str(current.commission_rate_percent) if current is not None else None
                ),
            },
        )

        return created
