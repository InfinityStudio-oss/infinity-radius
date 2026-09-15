"""Tenant wallet accounting. LEDGER_ENTRIES IS THE FINANCIAL SOURCE OF
TRUTH — tenant_wallets is only ever a summarized current-state cache
derived from it. Every method here that changes a wallet balance:

1. runs inside the caller's transaction (no method commits — the router
   layer commits once, same as every other service in this codebase),
2. takes a `SELECT ... FOR UPDATE` row lock on the wallet before reading
   its current balance, so two concurrent operations on the same tenant's
   wallet serialize instead of racing into a lost update, and
3. writes an immutable LedgerEntry justifying exactly what changed and why.

No frontend ever computes a balance and no endpoint ever accepts a raw new
balance value — the only way to correct a wallet is `create_adjustment`,
which requires both an actor and a reason and is itself just another
immutable ledger entry.
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import LedgerDirection, LedgerEntryType, WalletBucket
from app.core.errors import DomainValidationError
from app.core.money import DEFAULT_CURRENCY, quantize_tzs
from app.core.pagination import ListParams
from app.models.finance import LedgerEntry, SettlementLog, TenantWallet
from app.repositories.finance import (
    LedgerEntryRepository,
    SettlementLogRepository,
    TenantWalletRepository,
)
from app.services.commercial_terms import CommercialTermsService

_BUCKET_COLUMNS: dict[WalletBucket, str] = {
    WalletBucket.AVAILABLE: "available_balance_tzs",
    WalletBucket.PENDING: "pending_balance_tzs",
    WalletBucket.RESERVED: "reserved_balance_tzs",
    WalletBucket.FROZEN: "frozen_balance_tzs",
    WalletBucket.TOTAL_DISBURSED: "total_disbursed_tzs",
}


@dataclass(frozen=True)
class CollectionResult:
    wallet: TenantWallet
    collection_entry: LedgerEntry
    platform_fee_entry: LedgerEntry
    tenant_share_entry: LedgerEntry
    platform_fee: Decimal
    tenant_share: Decimal


class WalletService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = TenantWalletRepository(db)
        self.ledger_repo = LedgerEntryRepository(db)
        self.settlement_repo = SettlementLogRepository(db)
        self.commercial_terms = CommercialTermsService(db)

    async def get_or_create_wallet(self, *, tenant_id: UUID) -> TenantWallet:
        stmt = select(TenantWallet).where(TenantWallet.tenant_id == tenant_id)
        result = await self.db.execute(stmt)
        wallet = result.scalar_one_or_none()
        if wallet is not None:
            return wallet
        return await self.repo.create(tenant_id=tenant_id, currency=DEFAULT_CURRENCY)

    async def list_ledger(
        self, *, tenant_id: UUID, params: ListParams
    ) -> tuple[list[LedgerEntry], int]:
        return await self.ledger_repo.list_paginated(tenant_id=tenant_id, params=params)

    async def _locked_wallet(self, *, tenant_id: UUID) -> TenantWallet:
        wallet = await self.get_or_create_wallet(tenant_id=tenant_id)
        locked = await self.repo.get_by_id_for_update(tenant_id=tenant_id, id=wallet.id)
        if locked is None:
            raise RuntimeError(f"Wallet {wallet.id} vanished between create and lock")
        return locked

    async def _move_bucket(
        self, *, wallet: TenantWallet, bucket: WalletBucket, delta: Decimal
    ) -> Decimal:
        """Applies `delta` (positive or negative) to one wallet bucket column
        and returns the new value. Never lets a bucket go negative."""
        column = _BUCKET_COLUMNS[bucket]
        new_value = Decimal(getattr(wallet, column)) + delta
        if new_value < 0:
            raise DomainValidationError(
                f"This operation would take {bucket.value}_balance_tzs below zero"
            )
        await self.repo.update(wallet, **{column: str(new_value)})
        return new_value

    async def process_collection(
        self,
        *,
        tenant_id: UUID,
        gross_amount: Decimal,
        reference_type: str,
        reference_id: UUID | None,
        description: str | None = None,
    ) -> CollectionResult:
        """The only path from a completed customer payment to money the
        tenant is owed. Splits the gross amount using the tenant's own
        configured commercial terms — never a hard-coded rate — and fails
        closed (DomainValidationError) if none are configured, rather than
        silently assuming a rate. Writes three entries: an informational
        COLLECTION record of the gross amount, a PLATFORM_FEE record of
        what the platform keeps, and the TENANT_SHARE entry that actually
        credits the tenant's pending balance (funds land in `pending`, not
        `available` — see settle_pending for the pending -> available move)."""
        if gross_amount <= 0:
            raise DomainValidationError("gross_amount must be positive")

        terms = await self.commercial_terms.require_active(tenant_id=tenant_id)
        rate = Decimal(terms.commission_rate_percent)
        platform_fee = quantize_tzs(gross_amount * rate / Decimal(100))
        tenant_share = gross_amount - platform_fee

        wallet = await self._locked_wallet(tenant_id=tenant_id)
        new_pending = await self._move_bucket(
            wallet=wallet, bucket=WalletBucket.PENDING, delta=tenant_share
        )

        collection_entry = await self.ledger_repo.create(
            tenant_id=tenant_id,
            wallet_id=wallet.id,
            entry_type=LedgerEntryType.COLLECTION.value,
            direction=LedgerDirection.CREDIT.value,
            wallet_bucket=None,
            amount=str(gross_amount),
            balance_after=None,
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )
        platform_fee_entry = await self.ledger_repo.create(
            tenant_id=tenant_id,
            wallet_id=wallet.id,
            entry_type=LedgerEntryType.PLATFORM_FEE.value,
            direction=LedgerDirection.DEBIT.value,
            wallet_bucket=None,
            amount=str(platform_fee),
            balance_after=None,
            reference_type=reference_type,
            reference_id=reference_id,
            description=f"Platform commission at {rate}% of gross {gross_amount}",
        )
        tenant_share_entry = await self.ledger_repo.create(
            tenant_id=tenant_id,
            wallet_id=wallet.id,
            entry_type=LedgerEntryType.TENANT_SHARE.value,
            direction=LedgerDirection.CREDIT.value,
            wallet_bucket=WalletBucket.PENDING.value,
            amount=str(tenant_share),
            balance_after=str(new_pending),
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

        return CollectionResult(
            wallet=wallet,
            collection_entry=collection_entry,
            platform_fee_entry=platform_fee_entry,
            tenant_share_entry=tenant_share_entry,
            platform_fee=platform_fee,
            tenant_share=tenant_share,
        )

    async def create_adjustment(
        self,
        *,
        tenant_id: UUID,
        wallet_bucket: WalletBucket,
        direction: LedgerDirection,
        amount: Decimal,
        reason: str,
        actor_id: UUID,
        reference_type: str | None = None,
        reference_id: UUID | None = None,
    ) -> LedgerEntry:
        """The ONLY way to manually correct a wallet. There is no "set
        balance to X" path anywhere in this codebase — an admin can only
        request a signed delta against one bucket, with a mandatory reason
        and actor, recorded as an immutable ADJUSTMENT entry."""
        if amount <= 0:
            raise DomainValidationError("adjustment amount must be positive")
        if not reason or not reason.strip():
            raise DomainValidationError("An adjustment requires a non-empty reason")

        wallet = await self._locked_wallet(tenant_id=tenant_id)
        signed_delta = amount if direction is LedgerDirection.CREDIT else -amount
        new_balance = await self._move_bucket(
            wallet=wallet, bucket=wallet_bucket, delta=signed_delta
        )

        return await self.ledger_repo.create(
            tenant_id=tenant_id,
            wallet_id=wallet.id,
            entry_type=LedgerEntryType.ADJUSTMENT.value,
            direction=direction.value,
            wallet_bucket=wallet_bucket.value,
            amount=str(amount),
            balance_after=str(new_balance),
            reference_type=reference_type,
            reference_id=reference_id,
            description=reason,
            actor_id=actor_id,
        )

    async def settle_pending(
        self, *, tenant_id: UUID, amount: Decimal | None = None, batch_reference: str
    ) -> SettlementLog:
        """Moves collected-but-unsettled funds from `pending` into
        `available`, where a tenant can request a withdrawal against them.
        Tracked via settlement_logs rather than a ledger entry type — the
        8 ledger types this system recognizes don't include "settlement";
        settlement_logs is the source of truth for this specific bucket
        move, the same way withdrawals.status is for reserve/disburse."""
        wallet = await self._locked_wallet(tenant_id=tenant_id)
        pending = Decimal(wallet.pending_balance_tzs)
        settle_amount = pending if amount is None else amount
        if settle_amount <= 0:
            raise DomainValidationError("settle_pending amount must be positive")
        if settle_amount > pending:
            raise DomainValidationError("Cannot settle more than the current pending balance")

        await self._move_bucket(wallet=wallet, bucket=WalletBucket.PENDING, delta=-settle_amount)
        await self._move_bucket(
            wallet=wallet, bucket=WalletBucket.AVAILABLE, delta=settle_amount
        )

        return await self.settlement_repo.create(
            tenant_id=tenant_id,
            batch_reference=batch_reference,
            transaction_count=1,
            gross_amount=str(settle_amount),
            fee_amount="0",
            net_amount=str(settle_amount),
            status="settled",
        )

    async def reserve_for_withdrawal(self, *, tenant_id: UUID, amount: Decimal) -> TenantWallet:
        """available -> reserved, holding funds against an in-flight
        withdrawal request. No ledger entry — the Withdrawal row's own
        status is the source of truth for this hold, mirroring how a
        pending payment intent isn't itself a ledger event until it
        completes."""
        if amount <= 0:
            raise DomainValidationError("reserve amount must be positive")
        wallet = await self._locked_wallet(tenant_id=tenant_id)
        await self._move_bucket(wallet=wallet, bucket=WalletBucket.AVAILABLE, delta=-amount)
        await self._move_bucket(wallet=wallet, bucket=WalletBucket.RESERVED, delta=amount)
        return wallet

    async def release_reservation(self, *, tenant_id: UUID, amount: Decimal) -> TenantWallet:
        """reserved -> available — the exact reverse of reserve_for_withdrawal,
        for a withdrawal that never actually disbursed: rejected by a
        checker, cancelled by its requester, or its 2FA confirmation
        expired/exhausted. No ledger entry, same reasoning as
        reserve_for_withdrawal — Withdrawal.status (and its WithdrawalEvent
        trail) is the source of truth for why the hold was released."""
        if amount <= 0:
            raise DomainValidationError("release amount must be positive")
        wallet = await self._locked_wallet(tenant_id=tenant_id)
        await self._move_bucket(wallet=wallet, bucket=WalletBucket.RESERVED, delta=-amount)
        await self._move_bucket(wallet=wallet, bucket=WalletBucket.AVAILABLE, delta=amount)
        return wallet

    async def complete_disbursement(
        self,
        *,
        tenant_id: UUID,
        amount: Decimal,
        reference_type: str = "withdrawal",
        reference_id: UUID | None = None,
        description: str | None = None,
    ) -> LedgerEntry:
        """reserved -> total_disbursed once a payout actually leaves the
        platform. Writes the DISBURSEMENT entry against total_disbursed —
        the lifetime disbursed counter."""
        if amount <= 0:
            raise DomainValidationError("disbursement amount must be positive")
        wallet = await self._locked_wallet(tenant_id=tenant_id)
        await self._move_bucket(wallet=wallet, bucket=WalletBucket.RESERVED, delta=-amount)
        new_total = await self._move_bucket(
            wallet=wallet, bucket=WalletBucket.TOTAL_DISBURSED, delta=amount
        )
        return await self.ledger_repo.create(
            tenant_id=tenant_id,
            wallet_id=wallet.id,
            entry_type=LedgerEntryType.DISBURSEMENT.value,
            direction=LedgerDirection.CREDIT.value,
            wallet_bucket=WalletBucket.TOTAL_DISBURSED.value,
            amount=str(amount),
            balance_after=str(new_total),
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

    async def reverse_disbursement(
        self,
        *,
        tenant_id: UUID,
        amount: Decimal,
        reference_type: str = "withdrawal",
        reference_id: UUID | None = None,
        description: str | None = None,
    ) -> LedgerEntry:
        """A completed disbursement failed/was recalled at the provider
        (e.g. a bad mobile-money number) — total_disbursed -> available,
        net-of-reversal, with a DISBURSEMENT_REVERSAL entry against available."""
        if amount <= 0:
            raise DomainValidationError("reversal amount must be positive")
        wallet = await self._locked_wallet(tenant_id=tenant_id)
        await self._move_bucket(wallet=wallet, bucket=WalletBucket.TOTAL_DISBURSED, delta=-amount)
        new_available = await self._move_bucket(
            wallet=wallet, bucket=WalletBucket.AVAILABLE, delta=amount
        )
        return await self.ledger_repo.create(
            tenant_id=tenant_id,
            wallet_id=wallet.id,
            entry_type=LedgerEntryType.DISBURSEMENT_REVERSAL.value,
            direction=LedgerDirection.CREDIT.value,
            wallet_bucket=WalletBucket.AVAILABLE.value,
            amount=str(amount),
            balance_after=str(new_available),
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

    async def record_refund(
        self,
        *,
        tenant_id: UUID,
        amount: Decimal,
        reference_type: str = "transaction",
        reference_id: UUID | None = None,
        description: str | None = None,
    ) -> LedgerEntry:
        """A customer payment already credited to the tenant is refunded.
        Debits `available` — refunds are processed against settled funds;
        an unsettled (still-pending) collection should be corrected with
        record_reversal instead."""
        if amount <= 0:
            raise DomainValidationError("refund amount must be positive")
        wallet = await self._locked_wallet(tenant_id=tenant_id)
        new_available = await self._move_bucket(
            wallet=wallet, bucket=WalletBucket.AVAILABLE, delta=-amount
        )
        return await self.ledger_repo.create(
            tenant_id=tenant_id,
            wallet_id=wallet.id,
            entry_type=LedgerEntryType.REFUND.value,
            direction=LedgerDirection.DEBIT.value,
            wallet_bucket=WalletBucket.AVAILABLE.value,
            amount=str(amount),
            balance_after=str(new_available),
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

    async def record_reversal(
        self,
        *,
        tenant_id: UUID,
        amount: Decimal,
        reference_type: str = "transaction",
        reference_id: UUID | None = None,
        description: str | None = None,
    ) -> LedgerEntry:
        """Undoes a TENANT_SHARE that hasn't settled yet (e.g. a collection
        later found to be a duplicate/chargeback, caught before
        settle_pending moved it to available) — debits `pending`."""
        if amount <= 0:
            raise DomainValidationError("reversal amount must be positive")
        wallet = await self._locked_wallet(tenant_id=tenant_id)
        new_pending = await self._move_bucket(
            wallet=wallet, bucket=WalletBucket.PENDING, delta=-amount
        )
        return await self.ledger_repo.create(
            tenant_id=tenant_id,
            wallet_id=wallet.id,
            entry_type=LedgerEntryType.REVERSAL.value,
            direction=LedgerDirection.DEBIT.value,
            wallet_bucket=WalletBucket.PENDING.value,
            amount=str(amount),
            balance_after=str(new_pending),
            reference_type=reference_type,
            reference_id=reference_id,
            description=description,
        )

