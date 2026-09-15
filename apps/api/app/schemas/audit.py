from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID | None
    actor_id: UUID | None
    action: str
    target_type: str | None
    target_id: UUID | None
    # The ORM attribute is `log_metadata` (the DB column is `metadata`,
    # renamed on the model to avoid shadowing SQLAlchemy's own Base.metadata).
    metadata: dict[str, Any] | None = Field(
        default=None, validation_alias="log_metadata", serialization_alias="metadata"
    )
    created_at: datetime
