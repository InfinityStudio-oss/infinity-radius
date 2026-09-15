"""Onboarding request/response shapes. The request carries only public
registration/business data the client actually fills in — never
tenant_id, role, approval status, wallet balance, or feature flags. See
app/services/onboarding.py for exactly which of these fields end up
where.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.enums import BusinessType
from app.schemas.tenancy import TenantRead

_MIN_PASSWORD_LENGTH = 8


class OnboardingRegisterRequest(BaseModel):
    # --- Account Owner ---
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    work_email: EmailStr
    phone: str = Field(min_length=9, max_length=20)
    password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=128)
    confirm_password: str = Field(min_length=_MIN_PASSWORD_LENGTH, max_length=128)

    # --- Business Details ---
    trading_name: str = Field(min_length=2, max_length=200)
    legal_name: str | None = Field(default=None, max_length=200)
    business_type: BusinessType
    business_email: EmailStr
    business_phone: str = Field(min_length=9, max_length=20)
    tin: str | None = Field(default=None, max_length=50)
    business_license_number: str | None = Field(default=None, max_length=100)

    # --- Location ---
    # region/district/ward/street_area are no longer collected as separate
    # fields on the onboarding form — the client folds them into a single
    # free-text business_address ("Street/Ward - District - City/Region").
    # Kept here (and on Tenant) as optional/nullable for any future
    # structured entry (e.g. an admin editing a tenant's profile).
    region: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    ward: str | None = Field(default=None, max_length=100)
    street_area: str | None = Field(default=None, max_length=200)
    business_address: str = Field(min_length=1, max_length=500)

    # --- Authorized Contact — not collected on the onboarding form
    # (removed to keep signup to one short page); kept optional/nullable
    # on the model for a tenant to fill in later from their dashboard. ---
    authorized_contact_name: str | None = Field(default=None, max_length=200)
    authorized_contact_position: str | None = Field(default=None, max_length=100)
    authorized_contact_phone: str | None = Field(default=None, max_length=20)
    authorized_contact_email: EmailStr | None = None

    # --- Consent ---
    accept_terms: bool
    accept_privacy: bool

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        if not any(char.isdigit() for char in value):
            raise ValueError("Password must include at least one number")
        if not any(char.isalpha() for char in value):
            raise ValueError("Password must include at least one letter")
        return value

    @model_validator(mode="after")
    def _passwords_match(self) -> "OnboardingRegisterRequest":
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match")
        if not self.accept_terms:
            raise ValueError("You must accept the Terms of Service")
        if not self.accept_privacy:
            raise ValueError("You must accept the Privacy Policy")
        return self


class OnboardingRegisterResponse(BaseModel):
    """Deliberately minimal — no tenant internals, no auth tokens, no
    echoed input. Just enough for the frontend to render the
    "check your email" confirmation."""

    tenant_id: UUID
    status: str
    message: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class ResendVerificationResponse(BaseModel):
    sent: bool
    message: str


class TenantVerificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    status: str
    submitted_at: datetime | None
    email_verified_at: datetime | None
    reviewed_at: datetime | None
    reviewed_by: UUID | None
    approved_at: datetime | None
    rejected_at: datetime | None
    rejection_reason: str | None
    more_information_message: str | None


class AccountStatusRead(BaseModel):
    """What /account/pending-review and friends render — derived, never
    guessed, from the tenant + verification + Supabase email-confirmation
    state."""

    tenant_status: str
    email_verified: bool
    verification: TenantVerificationRead | None


class AdminTenantQueueRow(BaseModel):
    """One row of /super-admin/tenants — see AdminTenantService.list_queue."""

    id: UUID
    business_name: str
    owner_name: str | None
    owner_email: str | None
    # True when this tenant has no resolvable owner profile at all (e.g. the
    # sole profile that was tied to it was later converted to a platform
    # account) — distinct from owner_name/email simply being null for some
    # other reason, so the UI can show an honest "Owner record missing"
    # state instead of a blank field.
    owner_missing: bool
    business_type: str | None
    region: str | None
    email_verified: bool
    submitted_at: datetime | None
    status: str


class AdminTenantDetailRead(BaseModel):
    """/super-admin/tenants/{id} — every section the review page needs."""

    tenant: TenantRead
    owner_name: str | None
    owner_email: str | None
    owner_phone: str | None
    owner_missing: bool
    authorized_contact_name: str | None = None
    email_verified: bool
    verification: TenantVerificationRead | None
    # Independent of tenant.status — see AdminTenantService.set_collection_enabled/
    # set_payout_enabled. Approval never implies either of these.
    collection_enabled: bool
    payout_enabled: bool
    recent_audit_logs: list[dict[str, object]]


class AdminRejectTenantRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)


class AdminRequestMoreInformationRequest(BaseModel):
    message: str = Field(min_length=3, max_length=1000)


class AdminSetFeatureFlagRequest(BaseModel):
    enabled: bool


class TenantFeatureFlagsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    tenant_id: UUID
    collection_enabled: bool
    payout_enabled: bool
    api_enabled: bool


class AdminSuspendTenantRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)
