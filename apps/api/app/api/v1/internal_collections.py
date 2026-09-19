"""Internal service-to-service route: the Celery worker's ONLY path to
Selcom Collection order-status — mirrors app/api/v1/internal_disbursements.py
exactly (same HMAC scheme, same INTERNAL_WORKER_WEB_HMAC_KEY, same Option B
architecture), but for Collection instead of Disbursement. See
app/tasks/collections.py for the scheduled sweep that triggers it.

Reuses CollectionService.reconcile, which itself reuses
_apply_order_status (the exact same amount/currency/transid-validated,
query-only finalization code the webhook path already uses) — no
duplicate Selcom logic lives here. This route can only ever *query*
Selcom order-status; it has no access to create-order/wallet-payment and
must never gain one.
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.internal_auth import require_internal_auth
from app.db.session import get_db
from app.services.collections import CollectionService

logger = structlog.get_logger("api.internal_collections")

router = APIRouter()


class InternalCollectionReconcileRequest(BaseModel):
    """Deliberately minimal — no amount, result, payment_status, or
    provider reference from the worker; web alone decides what a query
    reveals and what to do about it."""

    transaction_id: UUID


class InternalCollectionReconcileResponse(BaseModel):
    """Deliberately minimal — no provider credentials, signature, or raw
    Selcom payload ever leaves this endpoint."""

    transaction_id: UUID
    status: str


@router.post(
    "/collections/reconcile",
    response_model=InternalCollectionReconcileResponse,
    dependencies=[Depends(require_internal_auth)],
)
async def reconcile_collection(
    payload: InternalCollectionReconcileRequest,
    db: AsyncSession = Depends(get_db),
) -> InternalCollectionReconcileResponse:
    service = CollectionService(db)
    transaction = await service.reconcile(transaction_id=payload.transaction_id)
    await db.commit()
    logger.info(
        "internal_collections.reconcile",
        transaction_id=str(transaction.id),
        status=transaction.status,
    )
    return InternalCollectionReconcileResponse(
        transaction_id=transaction.id, status=transaction.status
    )
