"""The full withdrawal lifecycle: a tenant owner requests a payout,
confirms a 2FA challenge, a different tenant owner/admin approves or
rejects it (maker-checker — the requester can never also be the
approver), and only on approval is it submitted to Selcom Disbursement.

Every balance change is row-locked (WalletService._locked_wallet) and
every status transition is recorded as an immutable WithdrawalEvent plus
an audit_logs entry — see app.core.enums.WithdrawalStatus for the full
state machine. Submission itself is guarded twice over against a double
payout: submit only ever runs from APPROVED (never re-entered once a
withdrawal has moved past it — see _submit_to_selcom), and a
tenant-level idempotency_key is generated once at request time and never
regenerated, so even a caller that somehow re-triggers submission sends
Selcom the same de-dup key rather than a fresh one.

Two independent gates must both be satisfied before any money moves
through this module:
  1. the tenant's own settlement mode (app/services/settlement_config.py)
     must be PLATFORM_MANAGED_WALLET — the default, DIRECT_MERCHANT_SETTLEMENT,
     means Infinity Radius does not hold or disburse this tenant's funds
     at all, and request_withdrawal refuses to run;
  2. Settings.selcom_disbursement_enabled (app/core/config.py) must be
     True — a platform-wide, explicit business/legal approval gate,
     independent of whether Selcom credentials happen to be configured.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import SettlementMode, WithdrawalStatus
from app.core.errors import DomainValidationError, NotFoundError
from app.core.money import DEFAULT_CURRENCY
from app.core.pagination import ListParams
from app.integrations.selcom.disbursement import SelcomDisbursementService
from app.integrations.selcom.exceptions import SelcomNotConfiguredError, SelcomNotImplementedError
from app.integrations.selcom.schemas import DisbursementOrderRequest
from app.models.finance import Withdrawal, WithdrawalDestination, WithdrawalEvent
from app.repositories.finance import (
    WithdrawalDestinationRepository,
    WithdrawalEventRepository,
    WithdrawalRepository,
)
from app.services.audit import write_audit_log
from app.services.captive_portal import selcom_config_from_settings
from app.services.settlement_config import SettlementConfigService
from app.services.two_factor import TwoFactorService
from app.services.wallet import WalletService

# The maker (whoever requested a withdrawal) can never also be its checker
# (whoever approves/rejects it) — enforced on every review action.
_MAKER_CHECKER_VIOLATION = "The withdrawal requester cannot also review it (maker-checker)"


@dataclass(frozen=True)
class TwoFactorConfirmationResult:
    withdrawal: Withdrawal
    verified: bool
    cancelled: bool  # True if this failed attempt exhausted retries/expiry and auto-cancelled


class PayoutService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WithdrawalRepository(db)
        self.destination_repo = WithdrawalDestinationRepository(db)
        self.event_repo = WithdrawalEventRepository(db)
        self.wallet_service = WalletService(db)
        self.settlement_config = SettlementConfigService(db)
        self.two_factor = TwoFactorService(db)

    # ------------------------------------------------------------ reads

    async def list_withdrawals(
        self, *, tenant_id: UUID, params: ListParams
    ) -> tuple[list[Withdrawal], int]:
        return await self.repo.list_paginated(tenant_id=tenant_id, params=params)

    async def get_withdrawal(self, *, tenant_id: UUID, withdrawal_id: UUID) -> Withdrawal:
        withdrawal = await self.repo.get_by_id(tenant_id=tenant_id, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        return withdrawal

    async def list_events(
        self, *, tenant_id: UUID, withdrawal_id: UUID
    ) -> list[WithdrawalEvent]:
        await self.get_withdrawal(tenant_id=tenant_id, withdrawal_id=withdrawal_id)
        return await self.event_repo.list_for_withdrawal(
            tenant_id=tenant_id, withdrawal_id=withdrawal_id
        )

    async def list_destinations(
        self, *, tenant_id: UUID, params: ListParams
    ) -> tuple[list[WithdrawalDestination], int]:
        return await self.destination_repo.list_paginated(tenant_id=tenant_id, params=params)

    async def create_destination(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        label: str,
        channel: str,
        account_name: str | None,
        account_number: str | None,
        is_default: bool,
    ) -> WithdrawalDestination:
        destination = await self.destination_repo.create(
            tenant_id=tenant_id,
            label=label,
            channel=channel,
            account_name=account_name,
            account_number=account_number,
            is_default=is_default,
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="withdrawal_destination.created",
            target_type="withdrawal_destination",
            target_id=destination.id,
        )
        return destination

    # ------------------------------------------------------- state machine

    async def _transition(
        self,
        withdrawal: Withdrawal,
        *,
        to_status: WithdrawalStatus,
        actor_id: UUID | None,
        reason: str | None = None,
    ) -> None:
        from_status = withdrawal.status
        await self.repo.update(withdrawal, status=to_status.value)
        await self.event_repo.create(
            tenant_id=withdrawal.tenant_id,
            withdrawal_id=withdrawal.id,
            from_status=from_status,
            to_status=to_status.value,
            actor_id=actor_id,
            reason=reason,
        )
        await write_audit_log(
            self.db,
            tenant_id=withdrawal.tenant_id,
            actor_id=actor_id,
            action=f"withdrawal.{to_status.value.lower()}",
            target_type="withdrawal",
            target_id=withdrawal.id,
            metadata={"reason": reason} if reason else None,
        )

    async def _fail_withdrawal(
        self, withdrawal: Withdrawal, *, reason: str, actor_id: UUID | None
    ) -> None:
        await self.wallet_service.release_reservation(
            tenant_id=withdrawal.tenant_id, amount=Decimal(withdrawal.amount)
        )
        await self.repo.update(
            withdrawal, failure_reason=reason, completed_at=datetime.now(UTC)
        )
        await self._transition(
            withdrawal, to_status=WithdrawalStatus.FAILED, actor_id=actor_id, reason=reason
        )

    # ------------------------------------------------------------- request

    async def request_withdrawal(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        destination_id: UUID,
        amount: Decimal,
    ) -> tuple[Withdrawal, str]:
        """Verifies balance, row-locks and reserves it, then issues a 2FA
        challenge. Returns (withdrawal, raw_two_factor_code) — the code is
        also written to the audit trail as an interim delivery channel
        (see app/services/two_factor.py's module docstring) but is handed
        back here too so a caller with a real delivery channel could use
        it directly once one exists."""
        if amount <= 0:
            raise DomainValidationError("amount must be greater than zero")

        destination = await self.destination_repo.get_by_id(tenant_id=tenant_id, id=destination_id)
        if destination is None:
            raise DomainValidationError("destination_id does not belong to this tenant")

        mode = await self.settlement_config.get_mode(tenant_id=tenant_id)
        if mode is not SettlementMode.PLATFORM_MANAGED_WALLET:
            raise DomainValidationError(
                "This tenant is configured for direct merchant settlement — Infinity "
                "Radius does not hold or disburse funds on this tenant's behalf. A "
                "super admin must switch this tenant to platform-managed wallet mode "
                "before withdrawals can be requested here."
            )

        if not get_settings().selcom_disbursement_enabled:
            raise DomainValidationError(
                "Selcom disbursement is disabled on this platform pending explicit "
                "business/legal approval and credentials."
            )

        try:
            wallet = await self.wallet_service.reserve_for_withdrawal(
                tenant_id=tenant_id, amount=amount
            )
        except DomainValidationError as exc:
            raise DomainValidationError(
                "Requested amount exceeds available wallet balance"
            ) from exc

        withdrawal = await self.repo.create(
            tenant_id=tenant_id,
            wallet_id=wallet.id,
            destination_id=destination_id,
            amount=str(amount),
            currency=DEFAULT_CURRENCY,
            status=WithdrawalStatus.DRAFT.value,
            requested_by=actor_id,
            idempotency_key=uuid4().hex,
        )
        await self.event_repo.create(
            tenant_id=tenant_id,
            withdrawal_id=withdrawal.id,
            from_status=None,
            to_status=WithdrawalStatus.DRAFT.value,
            actor_id=actor_id,
            reason=None,
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="withdrawal.requested",
            target_type="withdrawal",
            target_id=withdrawal.id,
            metadata={"amount": str(amount)},
        )

        code = await self.two_factor.issue_challenge(withdrawal)
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="withdrawal.two_factor_issued",
            target_type="withdrawal",
            target_id=withdrawal.id,
            metadata={
                "code": code,
                "expires_in_minutes": 10,
                "delivery": "audit_log_interim_channel — no SMS/email provider "
                "configured yet, see app/services/two_factor.py",
            },
        )

        return withdrawal, code

    # -------------------------------------------------------------- 2FA

    async def confirm_two_factor(
        self, *, tenant_id: UUID, withdrawal_id: UUID, actor_id: UUID, code: str
    ) -> TwoFactorConfirmationResult:
        withdrawal = await self.repo.get_by_id_for_update(tenant_id=tenant_id, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        if withdrawal.requested_by != actor_id:
            raise DomainValidationError("Only the requester can confirm this withdrawal's 2FA code")
        if withdrawal.status != WithdrawalStatus.DRAFT.value:
            raise DomainValidationError(
                f"Withdrawal is not awaiting 2FA confirmation (status: {withdrawal.status})"
            )

        verified = await self.two_factor.verify(withdrawal, code)
        if verified:
            await self._transition(
                withdrawal, to_status=WithdrawalStatus.PENDING_APPROVAL, actor_id=actor_id
            )
            return TwoFactorConfirmationResult(
                withdrawal=withdrawal, verified=True, cancelled=False
            )

        if self.two_factor.is_exhausted(withdrawal):
            await self.wallet_service.release_reservation(
                tenant_id=tenant_id, amount=Decimal(withdrawal.amount)
            )
            await self._transition(
                withdrawal,
                to_status=WithdrawalStatus.CANCELLED,
                actor_id=actor_id,
                reason="2FA confirmation failed too many times or the code expired",
            )
            return TwoFactorConfirmationResult(
                withdrawal=withdrawal, verified=False, cancelled=True
            )

        return TwoFactorConfirmationResult(withdrawal=withdrawal, verified=False, cancelled=False)

    # --------------------------------------------------------- maker-checker

    async def approve_withdrawal(
        self, *, tenant_id: UUID, withdrawal_id: UUID, actor_id: UUID, notes: str | None = None
    ) -> Withdrawal:
        withdrawal = await self.repo.get_by_id_for_update(tenant_id=tenant_id, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        if withdrawal.status != WithdrawalStatus.PENDING_APPROVAL.value:
            raise DomainValidationError(
                f"Withdrawal is not pending approval (status: {withdrawal.status})"
            )
        if withdrawal.requested_by == actor_id:
            raise DomainValidationError(_MAKER_CHECKER_VIOLATION)

        await self.repo.update(
            withdrawal, reviewed_by=actor_id, reviewed_at=datetime.now(UTC), review_notes=notes
        )
        await self._transition(
            withdrawal, to_status=WithdrawalStatus.APPROVED, actor_id=actor_id, reason=notes
        )

        await self._submit_to_selcom(withdrawal, actor_id=actor_id)
        return withdrawal

    async def reject_withdrawal(
        self, *, tenant_id: UUID, withdrawal_id: UUID, actor_id: UUID, reason: str
    ) -> Withdrawal:
        if not reason or not reason.strip():
            raise DomainValidationError("A rejection requires a reason")

        withdrawal = await self.repo.get_by_id_for_update(tenant_id=tenant_id, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        if withdrawal.status != WithdrawalStatus.PENDING_APPROVAL.value:
            raise DomainValidationError(
                f"Withdrawal is not pending approval (status: {withdrawal.status})"
            )
        if withdrawal.requested_by == actor_id:
            raise DomainValidationError(_MAKER_CHECKER_VIOLATION)

        await self.wallet_service.release_reservation(
            tenant_id=tenant_id, amount=Decimal(withdrawal.amount)
        )
        await self.repo.update(
            withdrawal,
            reviewed_by=actor_id,
            reviewed_at=datetime.now(UTC),
            review_notes=reason,
            completed_at=datetime.now(UTC),
        )
        await self._transition(
            withdrawal, to_status=WithdrawalStatus.REJECTED, actor_id=actor_id, reason=reason
        )
        return withdrawal

    async def cancel_withdrawal(
        self, *, tenant_id: UUID, withdrawal_id: UUID, actor_id: UUID, reason: str | None = None
    ) -> Withdrawal:
        withdrawal = await self.repo.get_by_id_for_update(tenant_id=tenant_id, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        if withdrawal.requested_by != actor_id:
            raise DomainValidationError("Only the requester can cancel this withdrawal")
        if withdrawal.status not in (
            WithdrawalStatus.DRAFT.value,
            WithdrawalStatus.PENDING_APPROVAL.value,
        ):
            raise DomainValidationError(
                f"Withdrawal can no longer be cancelled (status: {withdrawal.status})"
            )

        await self.wallet_service.release_reservation(
            tenant_id=tenant_id, amount=Decimal(withdrawal.amount)
        )
        await self.repo.update(withdrawal, completed_at=datetime.now(UTC))
        await self._transition(
            withdrawal, to_status=WithdrawalStatus.CANCELLED, actor_id=actor_id, reason=reason
        )
        return withdrawal

    async def reverse_withdrawal(
        self, *, tenant_id: UUID, withdrawal_id: UUID, actor_id: UUID | None, reason: str
    ) -> Withdrawal:
        """A SUCCESS'd disbursement turned out to be wrong (bad account,
        recalled by the provider) — total_disbursed -> available via
        WalletService.reverse_disbursement (writes a DISBURSEMENT_REVERSAL
        ledger entry), and the withdrawal itself moves to REVERSED.
        Exceptional/rare — see the SUPER_ADMIN-gated route in
        app/api/v1/tenants.py, mirroring the wallet-adjustment endpoint."""
        if not reason or not reason.strip():
            raise DomainValidationError("A reversal requires a reason")

        withdrawal = await self.repo.get_by_id_for_update(tenant_id=tenant_id, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        if withdrawal.status != WithdrawalStatus.SUCCESS.value:
            raise DomainValidationError(
                f"Only a successfully disbursed withdrawal can be reversed "
                f"(status: {withdrawal.status})"
            )

        await self.wallet_service.reverse_disbursement(
            tenant_id=tenant_id,
            amount=Decimal(withdrawal.amount),
            reference_id=withdrawal.id,
            description=reason,
        )
        await self._transition(
            withdrawal, to_status=WithdrawalStatus.REVERSED, actor_id=actor_id, reason=reason
        )
        return withdrawal

    # ------------------------------------------------------ Selcom submission

    async def _submit_to_selcom(self, withdrawal: Withdrawal, *, actor_id: UUID | None) -> None:
        """Never re-entrant: only ever runs immediately after
        approve_withdrawal transitions APPROVED, and the first thing it
        does is move to PROCESSING — so even if this were somehow called
        twice concurrently, the second caller's status check would see
        PROCESSING (or later) and refuse to submit again. Combined with
        the row lock held by approve_withdrawal's get_by_id_for_update
        call, this is the "never retry payout submission blindly"
        guarantee."""
        if withdrawal.status != WithdrawalStatus.APPROVED.value:
            return

        if not get_settings().selcom_disbursement_enabled:
            await self._fail_withdrawal(
                withdrawal,
                reason="Selcom disbursement is disabled on this platform pending "
                "explicit approval and credentials.",
                actor_id=actor_id,
            )
            return

        await self._transition(
            withdrawal, to_status=WithdrawalStatus.PROCESSING, actor_id=actor_id
        )
        await self.repo.update(withdrawal, submitted_at=datetime.now(UTC))

        destination = await self.destination_repo.get_by_id(
            tenant_id=withdrawal.tenant_id, id=withdrawal.destination_id
        )

        service = SelcomDisbursementService(selcom_config_from_settings())
        try:
            response = await service.initiate_disbursement(
                DisbursementOrderRequest(
                    reference=withdrawal.idempotency_key,
                    amount=Decimal(withdrawal.amount),
                    currency=withdrawal.currency,
                    recipient_phone=(destination.account_number if destination else None) or "",
                    recipient_name=destination.account_name if destination else None,
                )
            )
        except (SelcomNotConfiguredError, SelcomNotImplementedError) as exc:
            await self._fail_withdrawal(withdrawal, reason=str(exc), actor_id=actor_id)
            return

        if response.provider_reference:
            await self.repo.update(withdrawal, provider_reference=response.provider_reference)
        # Stays PROCESSING — apply_disbursement_result (via the Selcom
        # disbursement webhook, or a future query_disbursement poll)
        # resolves it to SUCCESS/FAILED. Never presumed here.

    async def apply_disbursement_result(
        self,
        *,
        withdrawal_id: UUID,
        provider_succeeded: bool,
        provider_reference: str,
        detail: str | None = None,
    ) -> Withdrawal:
        """Called by SelcomDisbursementService.process_callback once a
        disbursement callback has been genuinely verified. Tenant-agnostic
        lookup — same principle as CaptivePortalService.mark_transaction_completed:
        the provider_reference is the only thing identifying which
        withdrawal (and tenant) this is about."""
        withdrawal = await self.repo.get_by_id_for_update(tenant_id=None, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        if withdrawal.status != WithdrawalStatus.PROCESSING.value:
            # Already resolved (or never submitted) — idempotent no-op,
            # exactly like Transaction.status != "pending" in collection.py.
            return withdrawal

        if provider_succeeded:
            await self.wallet_service.complete_disbursement(
                tenant_id=withdrawal.tenant_id,
                amount=Decimal(withdrawal.amount),
                reference_id=withdrawal.id,
                description=f"Selcom disbursement {provider_reference}",
            )
            await self.repo.update(
                withdrawal, provider_reference=provider_reference, completed_at=datetime.now(UTC)
            )
            await self._transition(
                withdrawal, to_status=WithdrawalStatus.SUCCESS, actor_id=None, reason=detail
            )
        else:
            await self._fail_withdrawal(
                withdrawal,
                reason=detail or "Selcom reported disbursement failure",
                actor_id=None,
            )

        return withdrawal
