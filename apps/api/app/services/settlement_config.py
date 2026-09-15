"""Which disbursement architecture mode applies to a tenant — see
app.core.enums.SettlementMode. Never assume Infinity Radius holds a
tenant's funds: a tenant with no explicit configuration is treated as
DIRECT_MERCHANT_SETTLEMENT (Selcom settles with the tenant's own merchant
account; Infinity Radius's wallet is informational only), not the other
way around. Only an explicit, super-admin-authored row switches a tenant
to PLATFORM_MANAGED_WALLET, where the full withdrawal/maker-checker flow
in app/services/payouts.py applies.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SettlementMode
from app.core.errors import DomainValidationError
from app.models.finance import TenantSettlementConfig
from app.repositories.finance import TenantSettlementConfigRepository
from app.services.audit import write_audit_log


class SettlementConfigService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = TenantSettlementConfigRepository(db)

    async def get_active(self, *, tenant_id: UUID) -> TenantSettlementConfig | None:
        return await self.repo.get_active_for_tenant(tenant_id=tenant_id)

    async def get_mode(self, *, tenant_id: UUID) -> SettlementMode:
        config = await self.get_active(tenant_id=tenant_id)
        if config is None:
            return SettlementMode.DIRECT_MERCHANT_SETTLEMENT
        return SettlementMode(config.mode)

    async def set_mode(
        self,
        *,
        tenant_id: UUID,
        mode: SettlementMode,
        actor_id: UUID | None,
        notes: str | None = None,
    ) -> TenantSettlementConfig:
        """Versions the tenant's settlement mode: the current active row
        (if any) is deactivated and a new one inserted — never edited in
        place, so the full history of who changed a tenant's fund-custody
        arrangement, and when, is always retrievable."""
        current = await self.get_active(tenant_id=tenant_id)
        if current is not None and SettlementMode(current.mode) is mode:
            raise DomainValidationError(f"Tenant is already in {mode.value} mode")

        if current is not None:
            await self.repo.update(current, is_active=False)

        created = await self.repo.create(
            tenant_id=tenant_id,
            mode=mode.value,
            is_active=True,
            notes=notes,
            created_by=actor_id,
        )

        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="settlement_config.mode_changed",
            target_type="tenant_settlement_config",
            target_id=created.id,
            metadata={
                "mode": mode.value,
                "previous_mode": current.mode if current is not None else None,
            },
        )

        return created
