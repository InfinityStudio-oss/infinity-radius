from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import DestinationCode, LedgerDirection, SettlementMode, WalletBucket
from app.core.money import Money


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_id: UUID | None
    subscription_id: UUID | None
    reference: str
    provider_reference: str | None
    channel: str | None
    amount: Money
    currency: str
    status: str
    created_at: datetime
    updated_at: datetime


class WalletRead(BaseModel):
    """A SUMMARIZED, current-state view — see TenantWallet's docstring.
    ledger_entries is the source of truth; this is a read-only cache."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    currency: str
    available_balance_tzs: Money
    pending_balance_tzs: Money
    reserved_balance_tzs: Money
    frozen_balance_tzs: Money
    total_disbursed_tzs: Money
    created_at: datetime
    updated_at: datetime


class LedgerEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    wallet_id: UUID
    entry_type: str
    direction: str
    wallet_bucket: str | None
    amount: Money
    balance_after: Money | None
    reference_type: str | None
    reference_id: UUID | None
    description: str | None
    actor_id: UUID | None
    created_at: datetime


class WithdrawalDestinationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    label: str
    channel: str
    destination_code: str | None
    account_name: str | None
    account_number: str | None
    is_default: bool
    created_at: datetime


class WithdrawalDestinationCreate(BaseModel):
    label: str
    channel: str
    destination_code: DestinationCode
    account_name: str | None = None
    account_number: str | None = None
    is_default: bool = False


class WithdrawalRead(BaseModel):
    """Never carries an OTP secret: no otp_hash, no plaintext code, no
    expiry/attempt internals — only what a tenant's finance team or a
    reviewing Super Admin legitimately needs to see. Super Admin review
    only ever sees `two_factor_confirmed_at` (i.e. "2FA Verified: Yes/No"
    once it's non-null) — never the code itself, which by the time a
    withdrawal is even visible to a Super Admin has already been
    consumed (see app/services/payouts.py.confirm_two_factor)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    wallet_id: UUID
    destination_id: UUID
    amount: Money
    currency: str
    status: str
    provider_reference: str | None
    failure_reason: str | None
    approval_required: bool
    verified_recipient_name: str | None
    provider_charge: Money | None
    provider_result_code: str | None
    provider_message: str | None
    requested_by: UUID | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    review_notes: str | None
    two_factor_confirmed_at: datetime | None
    submitted_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class WithdrawalCreate(BaseModel):
    destination_id: UUID
    amount: Money = Field(description="Amount to withdraw, as a decimal string, e.g. \"15000.00\"")


class WithdrawalLookupPreviewRequest(BaseModel):
    """A read-only, non-persisting Selcom account/lookup preview — shown to
    the tenant before they confirm a withdrawal. The eventual withdrawal
    submission independently re-runs this same lookup server-side
    immediately before transferring; this preview never itself authorizes
    anything and is never what gets stored as verified_recipient_name."""

    destination_id: UUID
    amount: Money


class WithdrawalLookupPreviewResult(BaseModel):
    account_name: str | None
    operator: str | None
    total_charges: Money | None
    approval_required: bool


class WithdrawalRequestResult(BaseModel):
    """Never carries the OTP itself — only confirms an email was (or
    wasn't) sent, and where, in masked form. See
    app/services/payouts.py.request_withdrawal / _issue_and_send_otp."""

    withdrawal: WithdrawalRead
    otp_sent: bool = Field(description="Whether the verification email was actually delivered")
    masked_email: str = Field(description='e.g. "p***@example.com"')
    expires_in_seconds: int


class WithdrawalOtpResendResult(BaseModel):
    """Same safe shape as WithdrawalRequestResult, without re-serializing
    the whole withdrawal — the resend endpoint doesn't change anything
    about it beyond the OTP itself."""

    otp_sent: bool
    masked_email: str
    expires_in_seconds: int


class WithdrawalTwoFactorConfirm(BaseModel):
    code: str = Field(min_length=6, max_length=6, description="The 6-digit OTP")


class WithdrawalApprovalRequest(BaseModel):
    notes: str | None = None


class WithdrawalRejectionRequest(BaseModel):
    reason: str = Field(min_length=1, description="Why this withdrawal is being rejected")


class WithdrawalCancellationRequest(BaseModel):
    reason: str | None = None


class WithdrawalReversalRequest(BaseModel):
    reason: str = Field(min_length=1, description="Why this completed disbursement is reversed")


class WithdrawalEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    withdrawal_id: UUID
    from_status: str | None
    to_status: str
    actor_id: UUID | None
    reason: str | None
    created_at: datetime


class TenantCommercialTermsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    commission_rate_percent: Money
    is_active: bool
    effective_from: datetime
    notes: str | None
    created_by: UUID | None
    created_at: datetime


class TenantCommercialTermsCreate(BaseModel):
    commission_rate_percent: Money = Field(
        description="Platform commission rate for this tenant, as a percentage (0-100), "
        "e.g. \"12.50\" for 12.5%."
    )
    notes: str | None = None


class WalletAdjustmentRequest(BaseModel):
    """The ONLY shape a manual wallet correction can take — a signed delta
    against one named bucket, with a mandatory reason. There is no field
    here (and never will be) for a new balance value."""

    wallet_bucket: WalletBucket
    direction: LedgerDirection
    amount: Money = Field(description="Positive amount to move, e.g. \"5000.00\"")
    reason: str = Field(min_length=1, description="Why this adjustment is being made")


class TenantSettlementConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    mode: SettlementMode
    is_active: bool
    effective_from: datetime
    notes: str | None
    created_by: UUID | None
    created_at: datetime


class TenantSettlementConfigCreate(BaseModel):
    mode: SettlementMode
    notes: str | None = None
