from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class CustomerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_number: str
    first_name: str | None
    last_name: str | None
    phone: str
    email: str | None
    username: str | None
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime


class CustomerCreate(BaseModel):
    # Optional: a captive-portal self-service signup collects only a phone
    # number (see app/services/captive_portal.py) — staff creating a
    # customer through the dashboard can still supply both.
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str
    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=32)
    notes: str | None = None
