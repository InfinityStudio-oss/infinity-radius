"""Periodic Selcom Business disbursement reconciliation — the safety net
for PROCESSING (never got a first authoritative result) and AMBIGUOUS
(resultcode 999, never retried) withdrawals: queries Selcom directly with
each one's own idempotency_key, exactly as app/services/payouts.py's
webhook-triggered path does, and applies whatever that reveals. Never
retries the transfer itself — see PayoutService._submit_to_selcom, which
this never calls.

Also runs the stale-withdrawal alert check (PayoutService.maybe_alert_stale)
on anything still unresolved after the query, and writes one
"withdrawal.reconciliation_swept" audit log per run summarizing counts —
the data behind the Super Admin reconciliation-health endpoint (see
app/api/v1/super_admin.py), so Beat/Worker health has a real, queryable
signal without a new table.
"""

import asyncio

import structlog

from app.core.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.services.audit import write_audit_log
from app.services.payouts import PayoutService

logger = structlog.get_logger("tasks.reconciliation")


async def _reconcile_pending_withdrawals() -> int:
    scanned = 0
    resolved = 0
    still_pending = 0
    failed = 0
    alerted = 0

    async with AsyncSessionLocal() as db:
        service = PayoutService(db)
        pending = await service.list_reconcilable_withdrawals()
        scanned = len(pending)

        for withdrawal in pending:
            status_before = withdrawal.status
            try:
                updated = await service.reconcile_withdrawal(withdrawal_id=withdrawal.id)
                if updated.status != status_before:
                    resolved += 1
                else:
                    still_pending += 1
                    if await service.maybe_alert_stale(updated):
                        alerted += 1
                await db.commit()
            except Exception:  # noqa: BLE001 — one bad row must never stop the sweep
                await db.rollback()
                failed += 1
                logger.warning(
                    "reconciliation.withdrawal_failed", withdrawal_id=str(withdrawal.id)
                )

        await write_audit_log(
            db,
            tenant_id=None,
            actor_id=None,
            action="withdrawal.reconciliation_swept",
            target_type=None,
            target_id=None,
            metadata={
                "scanned": scanned,
                "resolved": resolved,
                "still_pending": still_pending,
                "failed": failed,
                "alerted": alerted,
            },
        )
        await db.commit()

    return scanned


@celery_app.task(name="infinity_radius.reconcile_pending_withdrawals")  # type: ignore[untyped-decorator]
def reconcile_pending_withdrawals() -> int:
    return asyncio.run(_reconcile_pending_withdrawals())
