from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TenantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    legal_name: str | None = None
    slug: str
    business_type: str | None = None
    business_email: str | None = None
    business_phone: str | None = None
    tin: str | None = None
    business_license_number: str | None = None
    country: str
    region: str | None = None
    district: str | None = None
    ward: str | None = None
    street_area: str | None = None
    address: str | None = None
    authorized_contact_name: str | None = None
    authorized_contact_position: str | None = None
    authorized_contact_phone: str | None = None
    authorized_contact_email: str | None = None
    currency: str
    timezone: str
    status: str
    accepted_terms_at: datetime | None = None
    accepted_privacy_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class CurrentUserRead(BaseModel):
    id: UUID
    email: str | None
    full_name: str | None
    tenant_id: UUID | None
    tenant_name: str | None
    tenant_status: str | None
    roles: list[str]
