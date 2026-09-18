"""Internal service-to-service route: the Celery worker's ONLY path to
Selcom Business for disbursement reconciliation (see
app/integrations/internal_web/client.py for the worker-side caller and
app/tasks/reconciliation.py for the scheduled sweep that triggers it).

Option B network centralization — the worker never calls Selcom directly
and never holds Selcom credentials; only this web service does, so only
web's Railway Static Outbound IPs need Selcom whitelisting. Authenticated
by a dedicated HMAC scheme (app/core/internal_auth.py), never a tenant or
Super Admin JWT, and never trusted on Railway private networking alone.

Reuses PayoutService.reconcile_if_pending, which itself reuses
_reconcile_locked (the exact same query-only Selcom call and
provider-status-mapping code already used by the disbursement webhook and
the Super Admin requery endpoint) — no duplicate Selcom logic lives here.
This route can only ever *query* Selcom; it has no access to
transaction/process and must never gain one.
"""

from uuid import UUID

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.internal_auth import require_internal_auth
from app.db.session import get_db
from app.services.payouts import PayoutService

logger = structlog.get_logger("api.internal_disbursements")

router = APIRouter()


class InternalReconcileRequest(BaseModel):
    """Deliberately minimal — no transId, amount, destination, or force
    flag. The worker only ever tells web WHICH withdrawal to check; web
    alone decides what that means and what to do about it."""

    withdrawal_id: UUID


class InternalReconcileResponse(BaseModel):
    """Deliberately minimal — no provider credentials, signature, or raw
    Selcom payload ever leaves this endpoint."""

    withdrawal_id: UUID
    status: str
    reconciled: bool


@router.post(
    "/disbursements/reconcile",
    response_model=InternalReconcileResponse,
    dependencies=[Depends(require_internal_auth)],
)
async def reconcile_disbursement(
    payload: InternalReconcileRequest,
    db: AsyncSession = Depends(get_db),
) -> InternalReconcileResponse:
    service = PayoutService(db)
    withdrawal, reconciled = await service.reconcile_if_pending(
        withdrawal_id=payload.withdrawal_id
    )
    await db.commit()
    logger.info(
        "internal_disbursements.reconcile",
        withdrawal_id=str(withdrawal.id),
        status=withdrawal.status,
        reconciled=reconciled,
    )
    return InternalReconcileResponse(
        withdrawal_id=withdrawal.id, status=withdrawal.status, reconciled=reconciled
    )
