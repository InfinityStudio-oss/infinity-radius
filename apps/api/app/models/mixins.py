"""Shared column mixins. Every table uses a UUID primary key (generated
server-side by Postgres' `gen_random_uuid()`, via the pgcrypto extension
Supabase enables by default) and timestamptz created_at/updated_at columns
kept current by a database trigger (see the migration), not app code —
so they stay correct regardless of which connection performs the write.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=text("now()"),
        nullable=False,
    )
