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
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import (
    MOBILE_MONEY_DESTINATION_CODES,
    DestinationCode,
    EmailEventStatus,
    EmailEventType,
    SettlementMode,
    WithdrawalStatus,
)
from app.core.errors import DomainValidationError, NotFoundError, RateLimitedError
from app.core.money import DEFAULT_CURRENCY
from app.core.pagination import ListParams
from app.core.phone import normalize_tz_phone
from app.integrations.resend.service import ResendEmailService
from app.integrations.selcom_business.client import SelcomBusinessClient
from app.integrations.selcom_business.config import selcom_business_config_from_settings
from app.integrations.selcom_business.errors import (
    SelcomBusinessAPIError,
    SelcomBusinessError,
    SelcomBusinessTransportError,
    SelcomResultOutcome,
)
from app.integrations.selcom_business.schemas import interpret_resultcode, money_from_provider
from app.models.audit import AuditLog
from app.models.finance import Withdrawal, WithdrawalDestination, WithdrawalEvent
from app.models.onboarding import EmailEvent
from app.repositories.finance import (
    WithdrawalDestinationRepository,
    WithdrawalEventRepository,
    WithdrawalRepository,
)
from app.repositories.onboarding import TenantFeatureFlagsRepository, TenantVerificationRepository
from app.repositories.tenancy import ProfileRepository, TenantRepository
from app.schemas.finance import WithdrawalLookupPreviewResult
from app.services.audit import write_audit_log
from app.services.settlement_config import SettlementConfigService
from app.services.two_factor import TwoFactorService
from app.services.wallet import WalletService


def _mask_account(account_number: str | None) -> str | None:
    """Keeps only the last 4 digits visible — e.g. "255712345678" ->
    "********5678" — for anything shown outside the tenant's own
    authenticated view (the Super Admin review email)."""
    if not account_number:
        return None
    if len(account_number) <= 4:
        return "*" * len(account_number)
    return "*" * (len(account_number) - 4) + account_number[-4:]


def _mask_destination(*, channel: str, account_number: str | None) -> str:
    """Mobile numbers keep enough head+tail to stay recognizable to the
    tenant reading the OTP email (e.g. "2557******123"); bank/Selcom
    accounts keep only the last 4 digits (e.g. "************4567") — same
    convention as most banks' own SMS/email OTP templates."""
    if not account_number:
        return "the saved destination"
    if channel == "mobile_money" and len(account_number) > 7:
        return f"{account_number[:4]}{'*' * (len(account_number) - 7)}{account_number[-3:]}"
    return _mask_account(account_number) or "the saved destination"


def _mask_email(email: str) -> str:
    """"p***@example.com" — enough for the tenant to recognize their own
    inbox, never enough to reveal it to someone who doesn't already know
    it."""
    local, _, domain = email.partition("@")
    if not domain:
        return "***"
    return f"{local[0]}***@{domain}" if local else f"***@{domain}"


def _otp_expired(withdrawal: Withdrawal) -> bool:
    if withdrawal.two_factor_expires_at is None:
        return True
    expires_at = withdrawal.two_factor_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    return datetime.now(UTC) > expires_at

logger = structlog.get_logger("services.payouts")

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

    async def list_pending_super_admin_approval(self) -> list[Withdrawal]:
        """Platform-wide — the Super Admin withdrawal queue's Pending
        Approval tab. See app/api/v1/admin_withdrawals.py."""
        return await self.repo.list_pending_super_admin_approval()

    async def get_withdrawal_for_super_admin(self, *, withdrawal_id: UUID) -> Withdrawal:
        """Tenant-agnostic lookup — a platform reviewer isn't scoped to
        one tenant."""
        withdrawal = await self.repo.get_by_id(tenant_id=None, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        return withdrawal

    async def list_all_for_super_admin(
        self, *, params: ListParams
    ) -> tuple[list[Withdrawal], int]:
        """Every withdrawal, any tenant, any status — the broader
        operational view (see GET /api/v1/admin/withdrawals/all) distinct
        from list_pending_super_admin_approval's narrower approval queue.
        `?status=PROCESSING` (etc.) filters via the existing generic
        list_paginated mechanism — WithdrawalRepository already declares
        "status" as a filterable field."""
        return await self.repo.list_paginated(tenant_id=None, params=params)

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
        destination_code: DestinationCode,
        account_name: str | None,
        account_number: str | None,
        is_default: bool,
    ) -> WithdrawalDestination:
        """`destination_code` is the one canonical source of which Selcom
        FI a payout goes through (app.core.enums.DestinationCode) — never
        a free-typed string. Mobile-money account numbers are normalized
        to 255XXXXXXXXX here, once, so every later Selcom call and every
        displayed value use the same canonical form; bank account numbers
        are never touched."""
        if destination_code in MOBILE_MONEY_DESTINATION_CODES:
            if not account_number:
                raise DomainValidationError("A mobile money destination requires a phone number")
            try:
                account_number = normalize_tz_phone(account_number)
            except ValueError as exc:
                raise DomainValidationError(str(exc)) from exc

        destination = await self.destination_repo.create(
            tenant_id=tenant_id,
            label=label,
            channel=channel,
            destination_code=destination_code.value,
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

    # ------------------------------------------------------------- limits

    async def _enforce_withdrawal_limits(self, *, tenant_id: UUID, amount: Decimal) -> None:
        """Every limit defaults to None (unenforced) — see
        Settings.withdrawal_*_limit_* — until an operator makes a real
        product decision and sets one. Checked before any funds are
        reserved, alongside the other request_withdrawal gates. Daily
        totals are a UTC calendar-day boundary and count every status
        except CANCELLED/REJECTED/FAILED (see
        WithdrawalRepository.daily_totals)."""
        settings = get_settings()

        min_amount = settings.withdrawal_min_amount_tzs
        if min_amount is not None and amount < min_amount:
            raise DomainValidationError(
                f"Withdrawal amount is below the minimum of "
                f"{settings.withdrawal_min_amount_tzs} {DEFAULT_CURRENCY}"
            )
        if (
            settings.withdrawal_max_single_amount_tzs is not None
            and amount > settings.withdrawal_max_single_amount_tzs
        ):
            raise DomainValidationError(
                f"Withdrawal amount exceeds the maximum single withdrawal of "
                f"{settings.withdrawal_max_single_amount_tzs} {DEFAULT_CURRENCY}"
            )

        daily_limit = settings.withdrawal_daily_limit_tzs
        daily_count_limit = settings.withdrawal_daily_count_limit
        if daily_limit is None and daily_count_limit is None:
            return

        today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_total, daily_count = await self.repo.daily_totals(
            tenant_id=tenant_id, since=today_start
        )

        if daily_limit is not None and daily_total + amount > daily_limit:
            raise DomainValidationError(
                f"This withdrawal would exceed today's withdrawal limit of "
                f"{daily_limit} {DEFAULT_CURRENCY} for this tenant"
            )
        if daily_count_limit is not None and daily_count + 1 > daily_count_limit:
            raise DomainValidationError(
                f"This tenant has reached today's limit of {daily_count_limit} withdrawal(s)"
            )

    # ---------------------------------------------------------------- OTP

    async def _resolve_verified_email(self, *, tenant_id: UUID, actor_id: UUID) -> str:
        """The ONLY place a withdrawal OTP's destination address comes
        from — the requester's own profile email, itself only ever set
        from a verified Supabase Auth session (see app/core/security.py),
        never a value the frontend can pass in. Refuses closed if that
        email hasn't completed the real onboarding verification (see
        app/services/onboarding.py's use of Supabase's own
        email_confirmed_at, mirrored into TenantVerification.email_verified_at)."""
        profile = await ProfileRepository(self.db).get_by_id(tenant_id=tenant_id, id=actor_id)
        verification = await TenantVerificationRepository(self.db).get_by_tenant(
            tenant_id=tenant_id
        )
        if (
            profile is None
            or not profile.email
            or verification is None
            or verification.email_verified_at is None
        ):
            raise DomainValidationError("Email verification is required before withdrawals.")
        return profile.email

    async def _issue_and_send_otp(
        self, withdrawal: Withdrawal, *, email: str, actor_id: UUID, resend: bool
    ) -> tuple[bool, int]:
        """Generates a fresh OTP, emails it via Resend, and records a safe
        (code-free) EmailEvent + audit trail either way. Never raises on a
        delivery failure — the withdrawal simply stays DRAFT/awaiting-OTP
        so the tenant can resend or cancel (see app/api/v1/payouts.py)."""
        settings = get_settings()
        destination = await self.destination_repo.get_by_id(
            tenant_id=withdrawal.tenant_id, id=withdrawal.destination_id
        )
        tenant = await TenantRepository(self.db).get_by_id(tenant_id=None, id=withdrawal.tenant_id)
        masked_destination = _mask_destination(
            channel=destination.channel if destination else "",
            account_number=destination.account_number if destination else None,
        )

        code = await self.two_factor.issue_challenge(withdrawal, sent_to_email=email)
        await self.repo.update(
            withdrawal,
            otp_last_sent_at=datetime.now(UTC),
            otp_send_count=withdrawal.otp_send_count + 1,
        )

        result = await ResendEmailService().send_withdrawal_otp_email(
            to=email,
            tenant_name=tenant.name if tenant else str(withdrawal.tenant_id),
            amount=Decimal(withdrawal.amount),
            currency=withdrawal.currency,
            masked_destination=masked_destination,
            otp=code,
            ttl_seconds=settings.withdrawal_otp_ttl_seconds,
        )

        now = datetime.now(UTC)
        self.db.add(
            EmailEvent(
                tenant_id=withdrawal.tenant_id,
                recipient=email,
                email_type=EmailEventType.WITHDRAWAL_OTP.value,
                provider_message_id=result.provider_message_id,
                status=(
                    EmailEventStatus.SENT.value if result.sent else EmailEventStatus.FAILED.value
                ),
                sent_at=now if result.sent else None,
                failed_at=None if result.sent else now,
                error_message=result.error_message,
            )
        )
        await self.db.flush()

        await write_audit_log(
            self.db,
            tenant_id=withdrawal.tenant_id,
            actor_id=actor_id,
            action="withdrawal.otp_resent" if resend else "withdrawal.otp_sent",
            target_type="withdrawal",
            target_id=withdrawal.id,
            metadata=None if result.sent else {"delivery_failed": True},
        )

        return result.sent, settings.withdrawal_otp_ttl_seconds

    async def resend_otp(
        self, *, tenant_id: UUID, withdrawal_id: UUID, actor_id: UUID
    ) -> tuple[Withdrawal, bool, str, int]:
        """Issues a brand new OTP, immediately invalidating the previous
        one (issue_challenge always overwrites the stored hash/expiry/
        attempt-counter — there is no path where both an old and new code
        are simultaneously valid). Rate-limited by both a cooldown and a
        per-withdrawal send cap so this can't be used to spam a tenant's
        inbox or brute-force-by-resend."""
        withdrawal = await self.repo.get_by_id_for_update(tenant_id=tenant_id, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        if withdrawal.requested_by != actor_id:
            raise DomainValidationError(
                "Only the requester can resend this withdrawal's verification code"
            )
        if withdrawal.status != WithdrawalStatus.DRAFT.value:
            raise DomainValidationError(
                f"Withdrawal is not awaiting a verification code (status: {withdrawal.status})"
            )

        settings = get_settings()
        if withdrawal.otp_send_count >= settings.withdrawal_otp_max_sends:
            raise DomainValidationError(
                "Maximum number of verification code sends reached for this withdrawal — "
                "cancel it and start a new withdrawal, or contact support."
            )
        if withdrawal.otp_last_sent_at is not None:
            last_sent = withdrawal.otp_last_sent_at
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=UTC)
            elapsed = (datetime.now(UTC) - last_sent).total_seconds()
            remaining = settings.withdrawal_otp_resend_cooldown_seconds - elapsed
            if remaining > 0:
                retry_after = int(remaining) + 1
                raise RateLimitedError(
                    f"Please wait {retry_after} seconds before requesting a new code.",
                    retry_after_seconds=retry_after,
                )

        email = await self._resolve_verified_email(tenant_id=tenant_id, actor_id=actor_id)
        otp_sent, expires_in = await self._issue_and_send_otp(
            withdrawal, email=email, actor_id=actor_id, resend=True
        )
        return withdrawal, otp_sent, _mask_email(email), expires_in

    # ------------------------------------------------------------- request

    async def request_withdrawal(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        destination_id: UUID,
        amount: Decimal,
    ) -> tuple[Withdrawal, bool, str, int]:
        """Verifies balance, row-locks and reserves it, then emails a
        fresh OTP to the requester's own verified email. Returns
        (withdrawal, otp_sent, masked_email, expires_in_seconds) — the raw
        code itself is never returned here or by any other response; see
        _issue_and_send_otp and app/services/two_factor.py."""
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

        flags = await TenantFeatureFlagsRepository(self.db).get_by_tenant(tenant_id=tenant_id)
        if flags is None or not flags.payout_enabled:
            raise DomainValidationError(
                "Payouts are not enabled for this tenant — a super admin must enable "
                "the payout feature flag before withdrawals can be requested."
            )

        # Resolved and validated before anything touches the wallet — a
        # tenant whose owner email isn't verified never gets as far as a
        # funds reservation.
        email = await self._resolve_verified_email(tenant_id=tenant_id, actor_id=actor_id)

        await self._enforce_withdrawal_limits(tenant_id=tenant_id, amount=amount)

        threshold = get_settings().selcom_withdrawal_approval_threshold_tzs
        approval_required = amount > threshold

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
            approval_required=approval_required,
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
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="withdrawal.otp_requested",
            target_type="withdrawal",
            target_id=withdrawal.id,
            metadata=None,
        )

        otp_sent, expires_in = await self._issue_and_send_otp(
            withdrawal, email=email, actor_id=actor_id, resend=False
        )

        return withdrawal, otp_sent, _mask_email(email), expires_in

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

        profile = await ProfileRepository(self.db).get_by_id(tenant_id=tenant_id, id=actor_id)
        current_email = profile.email if profile else None

        # Determined before verify() (which mutates two_factor_attempts on
        # a wrong guess) so a genuinely-expired code is reported as
        # otp_expired rather than otp_failed even on its first attempt.
        was_already_expired = _otp_expired(withdrawal)

        verified = await self.two_factor.verify(withdrawal, code, current_email=current_email)
        if verified:
            await write_audit_log(
                self.db,
                tenant_id=tenant_id,
                actor_id=actor_id,
                action="withdrawal.otp_verified",
                target_type="withdrawal",
                target_id=withdrawal.id,
                metadata=None,
            )
            if withdrawal.approval_required:
                await self._transition(
                    withdrawal, to_status=WithdrawalStatus.PENDING_APPROVAL, actor_id=actor_id
                )
                await self._send_super_admin_review_email(withdrawal)
            else:
                # At/under the threshold: no human approval step at all —
                # straight to APPROVED and submit, exactly the same path
                # a SUPER_ADMIN's approve_withdrawal takes for the
                # over-threshold case.
                await self._transition(
                    withdrawal, to_status=WithdrawalStatus.APPROVED, actor_id=actor_id
                )
                await self._submit_to_selcom(withdrawal, actor_id=actor_id)
            return TwoFactorConfirmationResult(
                withdrawal=withdrawal, verified=True, cancelled=False
            )

        if self.two_factor.is_exhausted(withdrawal):
            settings = get_settings()
            locked = withdrawal.two_factor_attempts >= settings.withdrawal_otp_max_attempts
            await write_audit_log(
                self.db,
                tenant_id=tenant_id,
                actor_id=actor_id,
                action="withdrawal.otp_locked" if locked else "withdrawal.otp_expired",
                target_type="withdrawal",
                target_id=withdrawal.id,
                metadata=None,
            )
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

        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="withdrawal.otp_expired" if was_already_expired else "withdrawal.otp_failed",
            target_type="withdrawal",
            target_id=withdrawal.id,
            metadata=None,
        )
        return TwoFactorConfirmationResult(withdrawal=withdrawal, verified=False, cancelled=False)

    # ------------------------------------------------------ SUPER_ADMIN review

    async def approve_withdrawal(
        self, *, withdrawal_id: UUID, actor_id: UUID, notes: str | None = None
    ) -> Withdrawal:
        """SUPER_ADMIN only — enforced by the route dependency
        (require_role(Role.SUPER_ADMIN)), never by this service checking
        who requested it. Cross-tenant lookup: a platform reviewer isn't
        scoped to one tenant. Only ever reachable for a withdrawal that
        was itself flagged approval_required at request time — an
        at/under-threshold withdrawal never enters PENDING_APPROVAL, so
        there is nothing for this method to act on for it."""
        withdrawal = await self.repo.get_by_id_for_update(tenant_id=None, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        if withdrawal.status != WithdrawalStatus.PENDING_APPROVAL.value:
            raise DomainValidationError(
                f"Withdrawal is not pending approval (status: {withdrawal.status})"
            )

        await self.repo.update(
            withdrawal, reviewed_by=actor_id, reviewed_at=datetime.now(UTC), review_notes=notes
        )
        await self._transition(
            withdrawal, to_status=WithdrawalStatus.APPROVED, actor_id=actor_id, reason=notes
        )

        await self._submit_to_selcom(withdrawal, actor_id=actor_id)
        return withdrawal

    async def reject_withdrawal(
        self, *, withdrawal_id: UUID, actor_id: UUID, reason: str
    ) -> Withdrawal:
        """SUPER_ADMIN only — see approve_withdrawal's docstring."""
        if not reason or not reason.strip():
            raise DomainValidationError("A rejection requires a reason")

        withdrawal = await self.repo.get_by_id_for_update(tenant_id=None, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        if withdrawal.status != WithdrawalStatus.PENDING_APPROVAL.value:
            raise DomainValidationError(
                f"Withdrawal is not pending approval (status: {withdrawal.status})"
            )

        await self.wallet_service.release_reservation(
            tenant_id=withdrawal.tenant_id, amount=Decimal(withdrawal.amount)
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

    # -------------------------------------------------------- Selcom lookup

    async def preview_lookup(
        self, *, tenant_id: UUID, destination_id: UUID, amount: Decimal
    ) -> WithdrawalLookupPreviewResult:
        """Display-only — shown to the tenant before they confirm a
        withdrawal. Never persists anything and is never what ends up
        stored as verified_recipient_name; the actual submission
        independently re-runs this same lookup server-side regardless
        (see _submit_to_selcom), so a tenant can never bypass verification
        by skipping this call or by tampering with its response."""
        destination = await self.destination_repo.get_by_id(
            tenant_id=tenant_id, id=destination_id
        )
        if destination is None:
            raise DomainValidationError("destination_id does not belong to this tenant")
        if not destination.destination_code or not destination.account_number:
            raise DomainValidationError("This destination has no verified account to look up")

        threshold = get_settings().selcom_withdrawal_approval_threshold_tzs
        client = SelcomBusinessClient(selcom_business_config_from_settings())
        try:
            response = await client.account_lookup(
                bank=destination.destination_code,
                account=destination.account_number,
                trans_id=f"lookup-{uuid4().hex}",
                amount=amount,
            )
        except SelcomBusinessError as exc:
            raise DomainValidationError(f"Could not verify destination account: {exc}") from exc

        data = response.data
        return WithdrawalLookupPreviewResult(
            account_name=data.account_name if data else None,
            operator=data.operator if data else None,
            total_charges=money_from_provider(data.total_charges) if data else None,
            approval_required=amount > threshold,
        )

    # ------------------------------------------------------ Selcom submission

    async def _submit_to_selcom(self, withdrawal: Withdrawal, *, actor_id: UUID | None) -> None:
        """Never re-entrant: only ever runs immediately after 2FA
        auto-approves an at/under-threshold withdrawal, or after a
        SUPER_ADMIN approves an over-threshold one — and the first thing
        it does (once past the account lookup) is move to PROCESSING, so
        even if this were somehow called twice concurrently, the second
        caller's status check would see PROCESSING (or later) and refuse
        to submit again. Combined with the row lock held by the caller's
        get_by_id_for_update call, this is the "never retry payout
        submission blindly" guarantee — transaction_process is called at
        most once per withdrawal, ever."""
        if withdrawal.status != WithdrawalStatus.APPROVED.value:
            return

        settings = get_settings()
        if not settings.selcom_disbursement_enabled:
            await self._fail_withdrawal(
                withdrawal,
                reason="Selcom disbursement is disabled on this platform pending "
                "explicit approval and credentials.",
                actor_id=actor_id,
            )
            return

        # Triple gate for real money: environment=production AND
        # disbursement_enabled=true (checked above) AND this, independently
        # true. Flipping SELCOM_BUSINESS_ENVIRONMENT to "production" (even
        # together with disbursement_enabled) is never, by itself, enough
        # to submit a real payout — see Settings.selcom_production_payouts_enabled.
        if (
            settings.selcom_business_environment == "production"
            and not settings.selcom_production_payouts_enabled
        ):
            await self._fail_withdrawal(
                withdrawal,
                reason="Production Selcom payouts are not enabled on this platform "
                "(SELCOM_PRODUCTION_PAYOUTS_ENABLED is not set).",
                actor_id=actor_id,
            )
            return

        destination = await self.destination_repo.get_by_id(
            tenant_id=withdrawal.tenant_id, id=withdrawal.destination_id
        )
        if (
            destination is None
            or not destination.destination_code
            or not destination.account_number
        ):
            await self._fail_withdrawal(
                withdrawal,
                reason="Withdrawal destination is missing or incomplete",
                actor_id=actor_id,
            )
            return

        client = SelcomBusinessClient(selcom_business_config_from_settings())

        # Re-verify the destination immediately before transferring — the
        # one and only source of verified_recipient_name. Never trust any
        # name a client supplied earlier via preview_lookup.
        try:
            lookup = await client.account_lookup(
                bank=destination.destination_code,
                account=destination.account_number,
                trans_id=f"{withdrawal.idempotency_key}-lookup",
                amount=Decimal(withdrawal.amount),
            )
        except SelcomBusinessTransportError as exc:
            # Unknown outcome, not a failure — never release funds or mark
            # FAILED for a lookup we simply couldn't complete.
            logger.warning(
                "payouts.lookup_transport_error", withdrawal_id=str(withdrawal.id), error=str(exc)
            )
            return
        except SelcomBusinessError as exc:
            await self._fail_withdrawal(withdrawal, reason=str(exc), actor_id=actor_id)
            return

        verified_name = lookup.data.account_name if lookup.data else None
        if not verified_name:
            await self._fail_withdrawal(
                withdrawal,
                reason="Selcom could not verify a recipient name for this destination",
                actor_id=actor_id,
            )
            return

        provider_charge = money_from_provider(lookup.data.total_charges) if lookup.data else None
        await self.repo.update(
            withdrawal, verified_recipient_name=verified_name, provider_charge=provider_charge
        )
        withdrawal.verified_recipient_name = verified_name

        await self._transition(
            withdrawal, to_status=WithdrawalStatus.PROCESSING, actor_id=actor_id
        )
        await self.repo.update(withdrawal, submitted_at=datetime.now(UTC))

        try:
            process_response = await client.transaction_process(
                trans_id=withdrawal.idempotency_key,
                recipient_fi_code=destination.destination_code,
                recipient_account=destination.account_number,
                recipient_name=verified_name,
                amount=Decimal(withdrawal.amount),
                purpose="FT",
                remarks=f"Infinity Radius withdrawal {withdrawal.idempotency_key}",
            )
        except SelcomBusinessTransportError as exc:
            # HTTP timeout/connection failure at the exact moment of
            # submission — the one truly dangerous case: Selcom may or may
            # not have received it. NEVER resubmit. Query with the SAME
            # transId to find out, and apply whatever that reveals.
            logger.warning(
                "payouts.process_transport_error", withdrawal_id=str(withdrawal.id), error=str(exc)
            )
            await self._reconcile_locked(withdrawal, actor_id=actor_id)
            return
        except SelcomBusinessAPIError as exc:
            await self._fail_withdrawal(withdrawal, reason=str(exc), actor_id=actor_id)
            return

        await self.repo.update(
            withdrawal,
            provider_reference=withdrawal.idempotency_key,
            provider_result_code=process_response.resultcode,
            provider_message=process_response.message,
        )
        await self._apply_provider_result(
            withdrawal,
            resultcode=process_response.resultcode,
            message=process_response.message,
            provider_amount=(
                money_from_provider(process_response.data.amount) if process_response.data else None
            ),
            provider_reference=(
                process_response.data.selcom_receipt if process_response.data else None
            )
            or withdrawal.idempotency_key,
            actor_id=actor_id,
        )

    async def _apply_provider_result(
        self,
        withdrawal: Withdrawal,
        *,
        resultcode: str | None,
        message: str | None,
        provider_amount: Decimal | None,
        provider_reference: str,
        actor_id: UUID | None,
    ) -> None:
        """The one place a Selcom result (from a direct process/query
        response, a reconciliation query, or a callback-triggered query)
        is turned into a withdrawal state change. Never called with an
        unauthenticated callback payload's own claims — always with a
        result this process obtained directly from an RSA-signed request."""
        if withdrawal.status not in (
            WithdrawalStatus.PROCESSING.value,
            WithdrawalStatus.AMBIGUOUS.value,
        ):
            return  # already resolved — idempotent no-op

        parsed = interpret_resultcode(resultcode=resultcode, message=message)

        if parsed.outcome == SelcomResultOutcome.SUCCESS:
            if provider_amount is not None and provider_amount != Decimal(withdrawal.amount):
                # Amount mismatch is exactly the spoofed/corrupted-signal
                # case this integration must never finalize on trust —
                # flag for manual review instead of either finalizing or
                # silently discarding it.
                await self.repo.update(
                    withdrawal,
                    provider_result_code=parsed.resultcode,
                    provider_message=f"Amount mismatch: provider reported {provider_amount}",
                )
                await self._transition(
                    withdrawal,
                    to_status=WithdrawalStatus.AMBIGUOUS,
                    actor_id=actor_id,
                    reason="Provider-reported amount does not match the withdrawal amount",
                )
                return

            await self.wallet_service.complete_disbursement(
                tenant_id=withdrawal.tenant_id,
                amount=Decimal(withdrawal.amount),
                reference_id=withdrawal.id,
                description=f"Selcom disbursement {provider_reference}",
            )
            await self.repo.update(
                withdrawal,
                provider_reference=provider_reference,
                provider_result_code=parsed.resultcode,
                provider_message=message,
                completed_at=datetime.now(UTC),
            )
            await self._transition(
                withdrawal, to_status=WithdrawalStatus.SUCCESS, actor_id=actor_id, reason=message
            )
        elif parsed.outcome == SelcomResultOutcome.INPROGRESS:
            # Stays PROCESSING — funds stay reserved, nothing finalized.
            # Reconciliation (Celery beat or a later callback) resolves it.
            await self.repo.update(
                withdrawal, provider_result_code=parsed.resultcode, provider_message=message
            )
        elif parsed.outcome == SelcomResultOutcome.AMBIGUOUS:
            # Never retried. Funds stay reserved until reconciliation
            # resolves it or a SUPER_ADMIN reviews it operationally.
            await self.repo.update(
                withdrawal, provider_result_code=parsed.resultcode, provider_message=message
            )
            await self._transition(
                withdrawal,
                to_status=WithdrawalStatus.AMBIGUOUS,
                actor_id=actor_id,
                reason=message or "Selcom resultcode 999 — status unknown, never retried",
            )
        else:
            await self.repo.update(
                withdrawal, provider_result_code=parsed.resultcode, provider_message=message
            )
            await self._fail_withdrawal(
                withdrawal,
                reason=message or f"Selcom reported failure (resultcode {parsed.resultcode})",
                actor_id=actor_id,
            )

    async def _reconcile_locked(self, withdrawal: Withdrawal, *, actor_id: UUID | None) -> None:
        """Queries Selcom with the withdrawal's own idempotency_key as
        transId — the only safe way to resolve a submission whose HTTP
        response was never received (timeout/connection error). Assumes
        the caller already holds this withdrawal's row lock."""
        client = SelcomBusinessClient(selcom_business_config_from_settings())
        try:
            query = await client.transaction_query(trans_id=withdrawal.idempotency_key)
        except SelcomBusinessTransportError:
            # Still unknown — leave it PROCESSING; a later reconciliation
            # pass (Celery beat) will try again. Never guess, never retry
            # the transfer itself.
            return
        except SelcomBusinessError as exc:
            logger.warning(
                "payouts.reconcile_query_error", withdrawal_id=str(withdrawal.id), error=str(exc)
            )
            return

        data = query.data
        status = (data.status if data else None) or ""
        resultcode = query.resultcode or {
            "COMPLETED": "000",
            "ACCEPTED": "111",
            "FAILED": "900",
        }.get(status, query.resultcode)
        await self._apply_provider_result(
            withdrawal,
            resultcode=resultcode,
            message=query.message,
            provider_amount=money_from_provider(data.amount) if data else None,
            provider_reference=(data.selcom_receipt if data else None)
            or withdrawal.idempotency_key,
            actor_id=actor_id,
        )

    async def reconcile_withdrawal(self, *, withdrawal_id: UUID) -> Withdrawal:
        """Public entry point for both the Selcom disbursement callback
        (see app/api/v1/webhooks.py) and the periodic Celery beat sweep
        (see app/core/celery_app.py) — a callback is only ever treated as
        a signal to query, never trusted to move money on its own claims."""
        withdrawal = await self.repo.get_by_id_for_update(tenant_id=None, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        await self._reconcile_locked(withdrawal, actor_id=None)
        return withdrawal

    async def reconcile_if_pending(self, *, withdrawal_id: UUID) -> tuple[Withdrawal, bool]:
        """Guarded entry point for app/api/v1/internal_disbursements.py (the
        worker's only path to Selcom, via the internal HMAC endpoint) —
        queries Selcom only when the withdrawal is still PROCESSING or
        AMBIGUOUS, and is a safe no-op for any terminal status (SUCCESS,
        FAILED, etc.), never re-querying a withdrawal reconciliation can no
        longer affect. Reuses _reconcile_locked (same lock, same
        provider-status-mapping code as reconcile_withdrawal/the webhook
        path) rather than duplicating any of it. Returns (withdrawal,
        reconciled) — reconciled is False whenever no Selcom call was made."""
        withdrawal = await self.repo.get_by_id_for_update(tenant_id=None, id=withdrawal_id)
        if withdrawal is None:
            raise NotFoundError("Withdrawal not found")
        if withdrawal.status not in (
            WithdrawalStatus.PROCESSING.value,
            WithdrawalStatus.AMBIGUOUS.value,
        ):
            return withdrawal, False
        await self._reconcile_locked(withdrawal, actor_id=None)
        return withdrawal, True

    async def list_reconcilable_withdrawals(self) -> list[Withdrawal]:
        """Every withdrawal a periodic reconciliation sweep should query —
        PROCESSING (awaiting a first authoritative result) or AMBIGUOUS
        (resultcode 999, never retried, only ever resolved by query)."""
        return await self.repo.list_by_statuses(
            statuses=[WithdrawalStatus.PROCESSING.value, WithdrawalStatus.AMBIGUOUS.value]
        )

    async def maybe_alert_stale(self, withdrawal: Withdrawal) -> bool:
        """Sends at most one Super Admin alert per cooldown window for a
        withdrawal reconciliation just checked and is STILL PROCESSING or
        AMBIGUOUS past its configured age threshold — never a payout
        retry, only a status email (see
        app/integrations/resend/templates/withdrawals.py). Dedup/cooldown
        is tracked via the audit trail itself (the most recent
        withdrawal.stale_alert_sent row for this withdrawal) rather than
        a new column/table. Returns True only if an alert was actually
        sent this call."""
        settings = get_settings()
        if withdrawal.status == WithdrawalStatus.PROCESSING.value:
            threshold_minutes = settings.withdrawal_processing_alert_minutes
        elif withdrawal.status == WithdrawalStatus.AMBIGUOUS.value:
            threshold_minutes = settings.withdrawal_ambiguous_alert_minutes
        else:
            return False

        reference_time = withdrawal.submitted_at or withdrawal.created_at
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=UTC)
        age_minutes = (datetime.now(UTC) - reference_time).total_seconds() / 60
        if age_minutes < threshold_minutes:
            return False

        last_alert_at = await self.db.scalar(
            select(AuditLog.created_at)
            .where(
                AuditLog.target_id == withdrawal.id,
                AuditLog.action == "withdrawal.stale_alert_sent",
            )
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        if last_alert_at is not None:
            if last_alert_at.tzinfo is None:
                last_alert_at = last_alert_at.replace(tzinfo=UTC)
            cooldown = timedelta(minutes=settings.withdrawal_stale_alert_cooldown_minutes)
            if datetime.now(UTC) - last_alert_at < cooldown:
                return False

        tenant = await TenantRepository(self.db).get_by_id(tenant_id=None, id=withdrawal.tenant_id)
        result = await ResendEmailService().send_stale_withdrawal_alert_email(
            withdrawal_id=withdrawal.id,
            tenant_name=tenant.name if tenant else str(withdrawal.tenant_id),
            amount=Decimal(withdrawal.amount),
            currency=withdrawal.currency,
            status=withdrawal.status,
            provider_reference=withdrawal.provider_reference,
            stuck_minutes=int(age_minutes),
        )
        await write_audit_log(
            self.db,
            tenant_id=withdrawal.tenant_id,
            actor_id=None,
            action="withdrawal.stale_alert_sent",
            target_type="withdrawal",
            target_id=withdrawal.id,
            metadata={
                "status": withdrawal.status,
                "stuck_minutes": int(age_minutes),
                "email_sent": result.sent,
            },
        )
        return result.sent

    async def _send_super_admin_review_email(self, withdrawal: Withdrawal) -> None:
        settings = get_settings()
        if not settings.super_admin_review_email:
            logger.info(
                "payouts.super_admin_review_email_skipped",
                reason="SUPER_ADMIN_REVIEW_EMAIL not configured",
                withdrawal_id=str(withdrawal.id),
            )
            return

        tenant = await TenantRepository(self.db).get_by_id(tenant_id=None, id=withdrawal.tenant_id)
        destination = await self.destination_repo.get_by_id(
            tenant_id=withdrawal.tenant_id, id=withdrawal.destination_id
        )
        result = await ResendEmailService().send_admin_withdrawal_review_email(
            tenant_name=tenant.name if tenant else str(withdrawal.tenant_id),
            amount=Decimal(withdrawal.amount),
            currency=withdrawal.currency,
            destination_channel=destination.channel if destination else "unknown",
            destination_code=destination.destination_code if destination else None,
            masked_account=_mask_account(destination.account_number if destination else None),
            withdrawal_reference=withdrawal.idempotency_key,
            requested_at=withdrawal.created_at,
            withdrawal_id=withdrawal.id,
        )
        action = (
            "withdrawal.super_admin_email_sent"
            if result.sent
            else "withdrawal.super_admin_email_failed"
        )
        await write_audit_log(
            self.db,
            tenant_id=withdrawal.tenant_id,
            actor_id=None,
            action=action,
            target_type="withdrawal",
            target_id=withdrawal.id,
        )

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
