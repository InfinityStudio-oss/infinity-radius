from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select

from app.models.finance import (
    LedgerEntry,
    PaymentWebhook,
    SettlementLog,
    TenantCommercialTerms,
    TenantSettlementConfig,
    TenantWallet,
    Transaction,
    Withdrawal,
    WithdrawalDestination,
    WithdrawalEvent,
)
from app.repositories.base import BaseRepository


class TransactionRepository(BaseRepository[Transaction]):
    model = Transaction
    search_fields = ("reference", "channel")
    filterable_fields = ("status", "channel", "customer_id")
    sortable_fields = ("created_at", "amount", "status")

    async def get_by_reference(self, *, reference: str) -> Transaction | None:
        """Tenant-agnostic on purpose: a webhook callback identifies a
        transaction by the internal reference we generated at initiation
        time (see app.integrations.selcom.collection), before we know
        which tenant it belongs to from the request alone — the same
        principle as resolving a router/transaction token."""
        stmt = select(Transaction).where(Transaction.reference == reference)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_reference_for_update(self, *, reference: str) -> Transaction | None:
        """Same as get_by_reference, but takes a row lock — see
        app.services.collections for why finalization (webhook,
        reconciliation, internal HMAC endpoint) always goes through this,
        never the unlocked lookup above."""
        stmt = select(Transaction).where(Transaction.reference == reference).with_for_update()
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_statuses(self, *, statuses: list[str]) -> list[Transaction]:
        stmt = select(Transaction).where(Transaction.status.in_(statuses))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


class PaymentWebhookRepository(BaseRepository[PaymentWebhook]):
    model = PaymentWebhook
    filterable_fields = ("provider", "processed", "signature_verified")
    sortable_fields = ("received_at",)
    default_sort = "-received_at"


class TenantWalletRepository(BaseRepository[TenantWallet]):
    model = TenantWallet
    sortable_fields = ("created_at",)


class LedgerEntryRepository(BaseRepository[LedgerEntry]):
    model = LedgerEntry
    filterable_fields = ("entry_type", "reference_type", "wallet_id")
    sortable_fields = ("created_at", "amount")


class WithdrawalDestinationRepository(BaseRepository[WithdrawalDestination]):
    model = WithdrawalDestination
    search_fields = ("label", "account_name", "account_number")
    filterable_fields = ("channel", "is_default")
    sortable_fields = ("created_at", "label")


class WithdrawalRepository(BaseRepository[Withdrawal]):
    model = Withdrawal
    filterable_fields = ("status", "wallet_id", "destination_id")
    sortable_fields = ("created_at", "amount", "status")

    async def get_by_provider_reference(self, *, provider_reference: str) -> Withdrawal | None:
        """Tenant-agnostic on purpose — a Selcom disbursement callback
        identifies a withdrawal by the provider's own order reference,
        before we know which tenant it belongs to from the request alone.
        Same principle as TransactionRepository.get_by_reference."""
        stmt = select(Withdrawal).where(Withdrawal.provider_reference == provider_reference)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, *, idempotency_key: str) -> Withdrawal | None:
        """Selcom Business disbursement callbacks/reconciliation identify a
        withdrawal by the transId WE supplied, which is always this
        withdrawal's own idempotency_key — see app/services/payouts.py."""
        stmt = select(Withdrawal).where(Withdrawal.idempotency_key == idempotency_key)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_statuses(self, *, statuses: list[str]) -> list[Withdrawal]:
        """Platform-wide (tenant-agnostic) — for the periodic Celery beat
        reconciliation sweep, see app/services/payouts.py.reconcile_withdrawal."""
        stmt = select(Withdrawal).where(Withdrawal.status.in_(statuses))
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_super_admin_approval(self) -> list[Withdrawal]:
        """Every withdrawal currently awaiting SUPER_ADMIN review — the
        Super Admin withdrawal queue's "Pending Approval" tab."""
        return await self.list_by_statuses(statuses=["PENDING_APPROVAL"])

    # Excluded from daily-limit totals: CANCELLED/REJECTED never actually
    # disbursed or even held a lasting reservation past the moment they
    # were voided, and FAILED released its reservation back — counting
    # them would needlessly restrict a tenant who simply hit a mistake or
    # a provider hiccup earlier in the day. Every other status (including
    # DRAFT — it's holding a live reservation right now) counts.
    _DAILY_LIMIT_EXCLUDED_STATUSES = ("CANCELLED", "REJECTED", "FAILED")

    async def daily_totals(
        self, *, tenant_id: UUID, since: datetime
    ) -> tuple[Decimal, int]:
        """(sum_amount, count) of this tenant's withdrawals requested at
        or after `since` (a UTC day boundary — see
        app/services/payouts.py._enforce_withdrawal_limits) that count
        toward WITHDRAWAL_DAILY_LIMIT_TZS/WITHDRAWAL_DAILY_COUNT_LIMIT."""
        stmt = select(
            func.coalesce(func.sum(Withdrawal.amount), 0), func.count(Withdrawal.id)
        ).where(
            Withdrawal.tenant_id == tenant_id,
            Withdrawal.created_at >= since,
            Withdrawal.status.not_in(self._DAILY_LIMIT_EXCLUDED_STATUSES),
        )
        result = await self.db.execute(stmt)
        total, count = result.one()
        return Decimal(total), int(count)


class WithdrawalEventRepository(BaseRepository[WithdrawalEvent]):
    model = WithdrawalEvent
    filterable_fields = ("withdrawal_id", "to_status")
    sortable_fields = ("created_at",)
    default_sort = "created_at"

    async def list_for_withdrawal(
        self, *, tenant_id: UUID, withdrawal_id: UUID
    ) -> list[WithdrawalEvent]:
        stmt = (
            self._base_query(tenant_id=tenant_id)
            .where(WithdrawalEvent.withdrawal_id == withdrawal_id)
            .order_by(WithdrawalEvent.created_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())


class SettlementLogRepository(BaseRepository[SettlementLog]):
    model = SettlementLog
    filterable_fields = ("status", "channel")
    sortable_fields = ("created_at", "settled_at")


class TenantCommercialTermsRepository(BaseRepository[TenantCommercialTerms]):
    model = TenantCommercialTerms
    filterable_fields = ("is_active",)
    sortable_fields = ("created_at", "effective_from")

    async def get_active_for_tenant(self, *, tenant_id: UUID) -> TenantCommercialTerms | None:
        stmt = (
            self._base_query(tenant_id=tenant_id)
            .where(TenantCommercialTerms.is_active.is_(True))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()


class TenantSettlementConfigRepository(BaseRepository[TenantSettlementConfig]):
    model = TenantSettlementConfig
    filterable_fields = ("is_active", "mode")
    sortable_fields = ("created_at", "effective_from")

    async def get_active_for_tenant(self, *, tenant_id: UUID) -> TenantSettlementConfig | None:
        stmt = (
            self._base_query(tenant_id=tenant_id)
            .where(TenantSettlementConfig.is_active.is_(True))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
