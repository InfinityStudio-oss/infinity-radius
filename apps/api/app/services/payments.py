from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.pagination import ListParams
from app.models.finance import Transaction
from app.repositories.finance import TransactionRepository


class PaymentService:
    """Read-only: transactions are written by the Selcom Collection webhook
    handler once that integration is implemented — see
    apps/api/app/integrations/selcom/. Never fabricated here."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = TransactionRepository(db)

    async def list(self, *, tenant_id: UUID, params: ListParams) -> tuple[list[Transaction], int]:
        return await self.repo.list_paginated(tenant_id=tenant_id, params=params)

    async def get(self, *, tenant_id: UUID, transaction_id: UUID) -> Transaction:
        transaction = await self.repo.get_by_id(tenant_id=tenant_id, id=transaction_id)
        if transaction is None:
            raise NotFoundError("Transaction not found")
        return transaction
