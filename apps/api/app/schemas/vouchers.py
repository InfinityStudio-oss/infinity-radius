from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.billing import SubscriptionRead


class VoucherBatchRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    package_id: UUID
    quantity: int
    prefix: str | None
    created_by: UUID | None
    created_at: datetime


class VoucherBatchCreate(BaseModel):
    package_id: UUID
    quantity: int = Field(gt=0, le=5000)
    prefix: str | None = Field(default=None, max_length=8)


class OfflineVoucherRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    batch_id: UUID
    code: str
    status: str
    redeemed_by_customer_id: UUID | None
    redeemed_subscription_id: UUID | None
    redeemed_at: datetime | None
    created_at: datetime


class VoucherRedeemRequest(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    customer_id: UUID


class VoucherRedeemResult(BaseModel):
    voucher: OfflineVoucherRead
    subscription: SubscriptionRead
