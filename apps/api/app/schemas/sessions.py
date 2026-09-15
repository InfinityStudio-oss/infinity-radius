from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    subscription_id: UUID | None
    customer_id: UUID | None
    router_id: UUID | None
    device_id: UUID | None
    session_identifier: str | None
    ip_address: str | None
    bytes_in: int
    bytes_out: int
    started_at: datetime | None
    ended_at: datetime | None
    status: str
    created_at: datetime
