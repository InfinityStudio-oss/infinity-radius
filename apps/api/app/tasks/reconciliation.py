"""Periodic Selcom Business disbursement reconciliation — the safety net
for PROCESSING (never got a first authoritative result) and AMBIGUOUS
(resultcode 999, never retried) withdrawals: queries Selcom directly with
each one's own idempotency_key, exactly as app/services/payouts.py's
webhook-triggered path does, and applies whatever that reveals. Never
retries the transfer itself — see PayoutService._submit_to_selcom, which
this never calls.
"""

import asyncio

import structlog

from app.core.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.services.payouts import PayoutService

logger = structlog.get_logger("tasks.reconciliation")


async def _reconcile_pending_withdrawals() -> int:
    async with AsyncSessionLocal() as db:
        service = PayoutService(db)
        pending = await service.list_reconcilable_withdrawals()
        for withdrawal in pending:
            try:
                await service.reconcile_withdrawal(withdrawal_id=withdrawal.id)
                await db.commit()
            except Exception:  # noqa: BLE001 — one bad row must never stop the sweep
                await db.rollback()
                logger.warning(
                    "reconciliation.withdrawal_failed", withdrawal_id=str(withdrawal.id)
                )
        return len(pending)


@celery_app.task(name="infinity_radius.reconcile_pending_withdrawals")  # type: ignore[untyped-decorator]
def reconcile_pending_withdrawals() -> int:
    return asyncio.run(_reconcile_pending_withdrawals())
