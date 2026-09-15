from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.pagination import ListParams
from app.models.network import UserSession
from app.repositories.sessions import UserSessionRepository


class SessionService:
    """Read-only: sessions are written by the RADIUS accounting integration
    (not yet implemented), never fabricated or edited via the API."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = UserSessionRepository(db)

    async def list(self, *, tenant_id: UUID, params: ListParams) -> tuple[list[UserSession], int]:
        return await self.repo.list_paginated(tenant_id=tenant_id, params=params)

    async def get(self, *, tenant_id: UUID, session_id: UUID) -> UserSession:
        session = await self.repo.get_by_id(tenant_id=tenant_id, id=session_id)
        if session is None:
            raise NotFoundError("Session not found")
        return session
