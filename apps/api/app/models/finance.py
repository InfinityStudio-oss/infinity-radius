"""Tenant-owned financial tables. Every money column is NUMERIC — never
float — and every currency defaults to TZS. `payment_webhooks.tenant_id`
is the one nullable exception: inbound webhooks arrive before the tenant
can be resolved from the payment reference.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Transaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A customer payment — Selcom Mobile Checkout Collection (STK push),
    see app/integrations/selcom_collection/ and app/services/collections.py.
    `reference` is OUR OWN server-generated order_id, sent to Selcom's
    create-order-minimal as `order_id` and used to look this row up from
    an inbound webhook/reconciliation (globally unique by construction,
    not just per-tenant — see CollectionService — since a webhook arrives
    before the tenant is known)."""

    __tablename__ = "transactions"
    __table_args__ = (UniqueConstraint("tenant_id", "reference"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    reference: Mapped[str] = mapped_column(Text, nullable=False)
    # Selcom Gateway's own payment identifier (order-status/webhook
    # `data.reference`) — "Available on COMPLETED payments only" per
    # Selcom's docs.
    provider_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Our own server-generated transid sent to wallet-payment (the STK
    # request's own idempotency key) — echoed back by Selcom on
    # completion. Never Selcom-supplied at request time.
    collection_transid: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Normalized 255XXXXXXXXX — the msisdn the STK prompt was sent to.
    payer_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    channel: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="TZS")
    # app.core.enums.CollectionStatus
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="CREATED")
    provider_resultcode: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    stk_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentWebhook(UUIDPrimaryKeyMixin, Base):
    """Raw inbound payment-provider callbacks, kept verbatim for audit/replay.
    tenant_id is nullable: it is resolved from the payload after receipt."""

    __tablename__ = "payment_webhooks"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="selcom")
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    signature_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    processed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TenantWallet(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A SUMMARIZED, current-state view of a tenant's finances — five
    independently-moving buckets. This is a cache, never the source of
    truth: every value here must equal the sum of that bucket's
    LedgerEntry credits minus debits, and the only code path allowed to
    change these columns is WalletService, inside a row-locked
    transaction that also writes the LedgerEntry justifying the change.
    No endpoint ever accepts a raw new balance — see WalletService.create_adjustment."""

    __tablename__ = "tenant_wallets"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="TZS")
    # Settled and immediately withdrawable.
    available_balance_tzs: Mapped[str] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    # Collected but not yet settled to available (see settle_pending).
    pending_balance_tzs: Mapped[str] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    # Held against an in-flight withdrawal request.
    reserved_balance_tzs: Mapped[str] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    # Held by an admin/dispute freeze — excluded from what a tenant can move.
    frozen_balance_tzs: Mapped[str] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )
    # Lifetime disbursed total, net of any DISBURSEMENT_REVERSAL.
    total_disbursed_tzs: Mapped[str] = mapped_column(
        Numeric(14, 2), nullable=False, server_default="0"
    )


class LedgerEntry(UUIDPrimaryKeyMixin, Base):
    """The financial source of truth. Immutable — no update/delete path is
    ever exposed; corrections are new ADJUSTMENT entries, never edits.
    entry_type/direction/wallet_bucket vocabularies are enforced both here
    (see app.core.enums) and by Postgres CHECK constraints."""

    __tablename__ = "ledger_entries"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_wallets.id", ondelete="CASCADE"), nullable=False
    )
    # COLLECTION | TENANT_SHARE | PLATFORM_FEE | REFUND | REVERSAL |
    # DISBURSEMENT | DISBURSEMENT_REVERSAL | ADJUSTMENT — app.core.enums.LedgerEntryType
    entry_type: Mapped[str] = mapped_column(Text, nullable=False)
    # credit | debit — app.core.enums.LedgerDirection. Explicit, never inferred.
    direction: Mapped[str] = mapped_column(Text, nullable=False)
    # Which TenantWallet column this entry moved — app.core.enums.WalletBucket.
    # Null for entries that don't move a tenant-owned bucket at all
    # (PLATFORM_FEE, the informational COLLECTION record).
    wallet_bucket: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False)
    balance_after: Mapped[str | None] = mapped_column(Numeric(14, 2), nullable=True)
    # transaction | withdrawal | settlement | adjustment
    reference_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Who caused this entry — null for system-generated entries (COLLECTION
    # splits). Always set for ADJUSTMENT, per the "immutable entry with
    # reason and actor" requirement.
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class TenantCommercialTerms(UUIDPrimaryKeyMixin, Base):
    """A tenant's platform commission rate. Never hard-coded and never
    edited in place — changing a rate deactivates the current row and
    inserts a new one, so the full rate-change history survives. Exactly
    one active row per tenant is enforced by a partial unique index
    (uq_tenant_commercial_terms_active)."""

    __tablename__ = "tenant_commercial_terms"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    commission_rate_percent: Mapped[str] = mapped_column(Numeric(5, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class SettlementLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "settlement_logs"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    batch_reference: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str | None] = mapped_column(Text, nullable=True)
    transaction_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    gross_amount: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    fee_amount: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    net_amount: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False, server_default="0")
    # pending | settled | failed
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class WithdrawalDestination(UUIDPrimaryKeyMixin, Base):
    """A tenant-configured payout destination (mobile money or bank)."""

    __tablename__ = "withdrawal_destinations"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(Text, nullable=False)
    # mobile_money | bank
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    # The specific Selcom FI code this destination pays out through — see
    # app.core.enums.DestinationCode. Nullable only for rows created before
    # this column existed; every new destination must set it (enforced in
    # PayoutService.create_destination, not just the DB CHECK constraint).
    destination_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class Withdrawal(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant payout request. Full maker-checker lifecycle — see
    app.core.enums.WithdrawalStatus for the 9 states and
    app/services/payouts.py for exactly which methods cause which
    transition. Every transition is also recorded as a WithdrawalEvent row.
    Never holds a secret in a client-readable form: two_factor_code_hash is
    a hash, never the raw code — see app/services/two_factor.py."""

    __tablename__ = "withdrawals"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    wallet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant_wallets.id", ondelete="RESTRICT"), nullable=False
    )
    destination_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("withdrawal_destinations.id", ondelete="RESTRICT"),
        nullable=False,
    )
    amount: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="TZS")
    # DRAFT | PENDING_APPROVAL | APPROVED | PROCESSING | SUCCESS | FAILED |
    # REJECTED | CANCELLED | REVERSED — app.core.enums.WithdrawalStatus
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="DRAFT")

    # Server-generated once at creation, never client-supplied. Passed to
    # Selcom's disbursement request as the de-dup key once implemented, and
    # used internally to guarantee submit_withdrawal never re-submits the
    # same request twice — see PayoutService._submit_to_selcom.
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    # Selcom's own disbursement order/transaction identifier, once a real
    # initiate_disbursement() call returns one.
    provider_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Persisted once at request time — whether this withdrawal ever needed
    # SUPER_ADMIN approval, per Settings.selcom_withdrawal_approval_threshold_tzs
    # AT THE TIME it was requested. Deliberately not re-derived from amount
    # later: if the threshold setting changes, past withdrawals' recorded
    # approval requirement must stay exactly what it was.
    approval_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    # The Selcom account/lookup-confirmed name actually used for transfer —
    # never a client-supplied override (see app/services/payouts.py).
    verified_recipient_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Selcom's own quoted/charged fee for this transfer (account/lookup's
    # totalCharges, or transaction/query's charges once available) — stored
    # for reconciliation, never silently debited from the tenant wallet
    # (no platform fee policy exists yet for withdrawal charges).
    provider_charge: Mapped[str | None] = mapped_column(Numeric(14, 2), nullable=True)
    provider_result_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    # The checker — whoever approved OR rejected this request. Maker-checker
    # is enforced in PayoutService: reviewed_by must never equal requested_by.
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Never exposed via any schema/response — a salted single-use hash with
    # a short expiry and an attempt counter, not a secret an API caller
    # should ever read back. See app/services/two_factor.py.
    two_factor_code_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    two_factor_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    two_factor_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    two_factor_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Resend-cooldown/cap bookkeeping for the OTP email — see
    # app/services/payouts.py's resend_otp and
    # Settings.withdrawal_otp_resend_cooldown_seconds/_max_sends.
    otp_last_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    otp_send_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # The exact address the current OTP was sent to, snapshotted at
    # issue/resend time — verification compares this against the
    # requester's live profile email and refuses if they've diverged
    # (e.g. the account's email changed mid-flow), rather than silently
    # accepting a code that was never actually seen by the current email.
    otp_sent_to_email: Mapped[str | None] = mapped_column(Text, nullable=True)


class WithdrawalEvent(UUIDPrimaryKeyMixin, Base):
    """Immutable status-transition log for one Withdrawal — distinct from
    ledger_entries (which is money movement only) and from audit_logs
    (platform-wide, every entity). This is the focused "what happened to
    this withdrawal, in order" history a tenant's finance team reviews."""

    __tablename__ = "withdrawal_events"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    withdrawal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("withdrawals.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    to_status: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class TenantSettlementConfig(UUIDPrimaryKeyMixin, Base):
    """Which architecture mode applies to this tenant — see
    app.core.enums.SettlementMode. Versioned exactly like
    TenantCommercialTerms: changing the mode deactivates the current row
    and inserts a new one, never edits in place; exactly one active row
    per tenant (uq_tenant_settlement_config_active)."""

    __tablename__ = "tenant_settlement_config"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # direct_merchant_settlement | platform_managed_wallet — app.core.enums.SettlementMode
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
