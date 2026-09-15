"""Audit trail writer, used by every other service on create/update/delete.
Append-only by design (see docs/rls-policies.md — `audit_logs` has no
client-facing write policy at all; this is the trusted backend path)."""

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import ListParams
from app.models.audit import AuditLog
from app.repositories.audit import AuditLogRepository


async def write_audit_log(
    db: AsyncSession,
    *,
    tenant_id: UUID | None,
    actor_id: UUID | None,
    action: str,
    target_type: str | None = None,
    target_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    repo = AuditLogRepository(db)
    await repo.create(
        tenant_id=tenant_id,
        actor_id=actor_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        log_metadata=metadata,
    )


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AuditLogRepository(db)

    async def list(
        self, *, tenant_id: UUID | None, params: ListParams
    ) -> tuple[list[AuditLog], int]:
        return await self.repo.list_paginated(tenant_id=tenant_id, params=params)
