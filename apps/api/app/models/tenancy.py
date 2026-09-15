"""Tenancy and RBAC: tenants, profiles (auth.users -> profile bridge), and
the role/permission system. See docs/rls-policies.md for how these back
`public.current_tenant_id()` and Row Level Security.
"""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.mixins import TimestampMixin, UUIDPrimaryKeyMixin


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """An ISP/hotspot provider. Every tenant-owned table carries tenant_id -> tenants.id.

    `name` is the trading/business name (what the onboarding form calls
    "Business / Trading Name") — kept as the original column rather than
    renamed to avoid a blast-radius rename across every service/schema/
    frontend reference already reading `tenant.name`. `legal_name` is new
    and optional, for when it differs from the trading name.
    """

    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    legal_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)

    # ISP | WISP | Hotspot Operator | ... — see app.core.enums.BusinessType.
    business_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    tin: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_license_number: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Localization defaults: Tanzania-wide, never a hard-coded city — the
    # tenant picks their own operating region/city via `locations`.
    country: Mapped[str] = mapped_column(Text, nullable=False, server_default="Tanzania")
    region: Mapped[str | None] = mapped_column(Text, nullable=True)
    district: Mapped[str | None] = mapped_column(Text, nullable=True)
    ward: Mapped[str | None] = mapped_column(Text, nullable=True)
    street_area: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional — the onboarding form's "Same as Account Owner" checkbox
    # means these are commonly left unset; the owner profile is then the
    # authorized contact by default.
    authorized_contact_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    authorized_contact_position: Mapped[str | None] = mapped_column(Text, nullable=True)
    authorized_contact_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    authorized_contact_email: Mapped[str | None] = mapped_column(Text, nullable=True)

    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="TZS")
    timezone: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="Africa/Dar_es_Salaam"
    )

    # PENDING_VERIFICATION | ACTIVE | MORE_INFORMATION_REQUIRED | REJECTED |
    # SUSPENDED — see app.core.enums.TenantStatus. The authoritative
    # tenant-facing status; tenant_verifications is the detailed review
    # record behind it.
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="PENDING_VERIFICATION"
    )

    accepted_terms_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_privacy_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Captive portal branding — tenant-supplied, null until they set it.
    # The portal falls back to Infinity Radius's own branding when unset;
    # never a fabricated logo/color.
    logo_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand_color: Mapped[str | None] = mapped_column(Text, nullable=True)


class Profile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Trusted extension of auth.users. `id` IS the auth.users.id (1:1, not a
    separate surrogate key) — this is what public.current_tenant_id() and
    every RLS policy reads, never the JWT's user-suppliable claims.
    """

    __tablename__ = "profiles"

    # No SQLAlchemy ForeignKey() here: auth.users lives outside this ORM's
    # metadata (Supabase-managed schema), and referencing it would break
    # relationship/join resolution for every other model. The actual FK
    # constraint is created with raw SQL in the initial_schema migration —
    # the database still enforces it, SQLAlchemy just doesn't model it.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=True,
    )

    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    full_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)

    # active | invited | disabled
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="invited")

    roles: Mapped[list["ProfileRole"]] = relationship(back_populates="profile")


class Role(UUIDPrimaryKeyMixin, Base):
    """Immutable, system-seeded role catalog — see app.core.roles.Role for the Python mirror."""

    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")


class Permission(UUIDPrimaryKeyMixin, Base):
    """Immutable, system-seeded permission catalog (e.g. 'billing.packages.manage')."""

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class RolePermission(Base):
    """Immutable, system-seeded role -> permission grants."""

    __tablename__ = "role_permissions"

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True
    )
    permission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True
    )


class ProfileRole(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A profile's role assignment. `tenant_id` is NULL only for the
    platform-wide SUPER_ADMIN role; every other role's tenant_id must match
    the profile's own tenant_id (enforced by trigger — see the migration).
    """

    __tablename__ = "profile_roles"
    __table_args__ = (UniqueConstraint("profile_id", "role_id", "tenant_id"),)

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )

    profile: Mapped[Profile] = relationship(back_populates="roles")
