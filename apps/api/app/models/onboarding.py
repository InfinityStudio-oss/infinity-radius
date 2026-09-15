"""Client signup + business onboarding + Super Admin approval workflow.

`TenantVerification` is the detailed review record; `Tenant.status`
mirrors it as the simpler tenant-facing summary. Both are written only by
`OnboardingService` (creation) and `AdminTenantService` (approve/reject/
request-more-information/suspend/reactivate) — never directly by a
tenant-scoped endpoint.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class TenantSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Minimal, extensible per-tenant preferences row — one per tenant,
    created empty at onboarding. Deliberately unopinionated about shape
    (no onboarding-specified fields exist yet beyond the row's existence);
    `preferences` is where future tenant-configurable settings land
    without another migration."""

    __tablename__ = "tenant_settings"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    preferences: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default="{}")


class TenantFeatureFlags(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Gates that must be explicitly turned on — never implied by tenant
    existence or ACTIVE status alone. All false at onboarding; only
    AdminTenantService.approve (per current platform policy) or a later
    explicit admin action ever flips them."""

    __tablename__ = "tenant_feature_flags"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    collection_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false"
    )
    payout_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    api_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class TenantVerification(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The Super Admin review record for one tenant's onboarding. One row
    per tenant — status transitions are also recorded as audit_logs
    entries (TENANT_REVIEWED/TENANT_APPROVED/...), this row is just the
    current state a review page reads."""

    __tablename__ = "tenant_verifications"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    # PENDING_VERIFICATION | APPROVED | MORE_INFORMATION_REQUIRED | REJECTED
    # — see app.core.enums.TenantVerificationStatus.
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="PENDING_VERIFICATION"
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    more_information_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class EmailEvent(UUIDPrimaryKeyMixin, Base):
    """Every Resend send attempt — onboarding and beyond. tenant_id is
    nullable to mirror payment_webhooks: a send can be attempted for
    context that doesn't cleanly resolve to one tenant."""

    __tablename__ = "email_events"

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True
    )
    recipient: Mapped[str] = mapped_column(Text, nullable=False)
    # VERIFY_EMAIL | NEW_TENANT_ADMIN_ALERT | TENANT_APPROVED | TENANT_REJECTED
    # | MORE_INFORMATION_REQUIRED | TENANT_SUSPENDED | TENANT_REACTIVATED
    email_type: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False, server_default="RESEND")
    provider_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SENT | FAILED
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="SENT")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        "metadata", JSONB, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
