from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import PackageActivationType, PackageStatus
from app.core.money import Money


class PackageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    description: str | None
    price_tzs: Money
    duration_minutes: int | None
    bytes_limit: int | None
    download_speed_kbps: int | None
    upload_speed_kbps: int | None
    device_limit: int
    simultaneous_sessions: int
    activation_type: str
    status: str
    created_at: datetime
    updated_at: datetime


class PackageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    price_tzs: Money
    duration_minutes: int | None = Field(default=None, gt=0)
    bytes_limit: int | None = Field(default=None, gt=0)
    download_speed_kbps: int | None = Field(default=None, gt=0)
    upload_speed_kbps: int | None = Field(default=None, gt=0)
    device_limit: int = Field(default=1, gt=0)
    simultaneous_sessions: int = Field(default=1, gt=0)
    activation_type: PackageActivationType = PackageActivationType.IMMEDIATE
    status: PackageStatus = PackageStatus.ACTIVE


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    customer_id: UUID
    package_id: UUID
    voucher_id: UUID | None
    status: str
    activated_at: datetime | None
    expires_at: datetime | None
    bytes_used: int
    created_at: datetime
    updated_at: datetime


class SubscriptionCreate(BaseModel):
    customer_id: UUID
    package_id: UUID
