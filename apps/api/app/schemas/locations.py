from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LocationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    name: str
    region: str | None
    city: str | None
    address: str | None
    latitude: Decimal | None
    longitude: Decimal | None
    timezone: str
    status: str
    created_at: datetime
    updated_at: datetime


class LocationCreate(BaseModel):
    name: str
    region: str | None = None
    city: str | None = None
    address: str | None = None
