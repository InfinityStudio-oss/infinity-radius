"""Tenant-owned network, billing-catalog, and subscriber tables.

Every table here carries a NOT NULL tenant_id and is RLS-protected — see
docs/rls-policies.md. No fake/sample rows are ever inserted by migrations;
these tables start and stay empty until real tenants create real data.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Location(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A tenant-chosen operating site. Region/city are tenant-selected —
    never hard-coded — anywhere within the tenant's country (Tanzania by default)."""

    __tablename__ = "locations"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="Africa/Dar_es_Salaam"
    )
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")


class Router(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A MikroTik RouterOS device, reached via the Network Agent over WireGuard."""

    __tablename__ = "routers"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    serial_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)
    management_ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    mac_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    firmware_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    # online | offline | degraded | unknown — real-only, reported by the Network Agent
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="unknown")
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Add Router Wizard (see app/services/router_provisioning.py) ---
    # in_progress | completed
    provisioning_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="in_progress"
    )
    # Hotspot LAN config (tenant-supplied — never a hard-coded network).
    hotspot_network_cidr: Mapped[str | None] = mapped_column(Text, nullable=True)
    hotspot_gateway_ip: Mapped[str | None] = mapped_column(Text, nullable=True)
    hotspot_dns_servers: Mapped[str | None] = mapped_column(Text, nullable=True)
    # WireGuard peer identity. The private key is encrypted at rest
    # (app.core.crypto); the public key and tunnel IP are not secret.
    wireguard_public_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    wireguard_tunnel_ip: Mapped[str | None] = mapped_column(Text, nullable=True, unique=True)
    wireguard_private_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    # RADIUS shared secret this router authenticates with — encrypted at rest.
    radius_secret_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)


class Package(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A WiFi access plan a tenant sells. Always priced in TZS — every
    tenant creates their own; nothing here is ever seeded as a default/sample
    package."""

    __tablename__ = "packages"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    price_tzs: Mapped[str] = mapped_column(Numeric(14, 2), nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bytes_limit: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    download_speed_kbps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    upload_speed_kbps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    device_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    simultaneous_sessions: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    # immediate | first_use — see app.core.enums.PackageActivationType
    activation_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="immediate"
    )
    # draft | active | archived — see app.core.enums.PackageStatus
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")


class Customer(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A hotspot end-customer. Phone is the primary identifier for TZ mobile
    money flows; customer_number is generated server-side (app/core sequence),
    never client-supplied."""

    __tablename__ = "customers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "phone"),
        UniqueConstraint("tenant_id", "customer_number"),
        UniqueConstraint("tenant_id", "username"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    customer_number: Mapped[str] = mapped_column(Text, nullable=False)
    # Nullable: a captive-portal self-service signup only ever collects a
    # phone number — see app/services/captive_portal.py.
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    username: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class CustomerDevice(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "customer_devices"
    __table_args__ = (UniqueConstraint("tenant_id", "mac_address"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    mac_address: Mapped[str] = mapped_column(Text, nullable=False)
    device_label: Mapped[str | None] = mapped_column(Text, nullable=True)


class Subscription(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "subscriptions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="CASCADE"), nullable=False
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("packages.id", ondelete="RESTRICT"), nullable=False
    )
    voucher_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("offline_vouchers.id", ondelete="SET NULL"), nullable=True
    )
    # PENDING | ACTIVE | EXPIRED | SUSPENDED | CANCELLED | QUOTA_EXCEEDED
    # see app.core.enums.SubscriptionStatus
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PENDING")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bytes_used: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")


class UserSession(UUIDPrimaryKeyMixin, Base):
    """A RADIUS-accounting-style connectivity session. created_at only — sessions are
    append-only accounting records, never edited after the fact."""

    __tablename__ = "user_sessions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    router_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("routers.id", ondelete="SET NULL"), nullable=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_devices.id", ondelete="SET NULL"), nullable=True
    )
    session_identifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    bytes_in: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    bytes_out: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # active | closed
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )


class VoucherBatch(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "voucher_batches"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("packages.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )


class OfflineVoucher(UUIDPrimaryKeyMixin, Base):
    """A prepaid scratch-card-style access code, redeemable without a live payment call."""

    __tablename__ = "offline_vouchers"
    __table_args__ = (UniqueConstraint("tenant_id", "code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("voucher_batches.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    # UNUSED | USED | EXPIRED | VOID — see app.core.enums.VoucherStatus
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="UNUSED")
    redeemed_by_customer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    redeemed_subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        server_default=text("now()"), nullable=False
    )
