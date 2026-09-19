"""Periodic Selcom Mobile Checkout Collection reconciliation — the safety
net for every non-terminal Collection order (CREATED, STK_SENT, PENDING,
INPROGRESS, AMBIGUOUS): Selcom's webhook only ever fires on a successful
transaction (per its own docs), so anything that fails, gets cancelled,
rejected, or simply never resolves needs this sweep to find out.

Option B network centralization, identical to app/tasks/reconciliation.py:
the worker never calls Selcom directly and holds no Selcom Collection
credentials. It only decides WHICH orders need reconciliation (pure DB
read, see CollectionService.list_reconcilable_collections) and asks web's
internal, HMAC-authenticated endpoint to actually query Selcom's
order-status — see app/integrations/internal_web/client.py and
app/api/v1/internal_collections.py, which reuses the exact same
amount/currency/transid-validated finalization code
(CollectionService._apply_order_status) the webhook path already uses.
This module must never import app.integrations.selcom_collection.client
or anything Selcom-Collection-credential-shaped.

Deliberately never resubmits a wallet-payment/STK — see
InternalWebClient.reconcile_collection, which can only ever reach
order-status on web's side (app/api/v1/internal_collections.py has no
access to create-order/wallet-payment at all).
"""

import asyncio

import structlog

from app.core.celery_app import celery_app
from app.db.session import AsyncSessionLocal
from app.integrations.internal_web.client import InternalWebClient, InternalWebNotConfiguredError
from app.services.audit import write_audit_log
from app.services.collections import CollectionService

logger = structlog.get_logger("tasks.collections")


async def _reconcile_pending_collections() -> int:
    scanned = 0
    resolved = 0
    still_pending = 0
    failed = 0

    async with AsyncSessionLocal() as db:
        service = CollectionService(db)
        pending = await service.list_reconcilable_collections()
        scanned = len(pending)

        try:
            client = InternalWebClient()
        except InternalWebNotConfiguredError:
            failed = scanned
            logger.error("collections_reconciliation.internal_web_not_configured", scanned=scanned)
            await write_audit_log(
                db,
                tenant_id=None,
                actor_id=None,
                action="collection.reconciliation_swept",
                target_type=None,
                target_id=None,
                metadata={
                    "scanned": scanned,
                    "resolved": 0,
                    "still_pending": 0,
                    "failed": failed,
                    "error": "internal_web_not_configured",
                },
            )
            await db.commit()
            return scanned

        async with client:
            for transaction in pending:
                status_before = transaction.status
                try:
                    result = await client.reconcile_collection(transaction_id=transaction.id)
                    if result.status != status_before:
                        resolved += 1
                    else:
                        still_pending += 1
                    await db.commit()
                except Exception:  # noqa: BLE001 — one bad row must never stop the sweep
                    await db.rollback()
                    failed += 1
                    logger.warning(
                        "collections_reconciliation.transaction_failed",
                        transaction_id=str(transaction.id),
                    )

        await write_audit_log(
            db,
            tenant_id=None,
            actor_id=None,
            action="collection.reconciliation_swept",
            target_type=None,
            target_id=None,
            metadata={
                "scanned": scanned,
                "resolved": resolved,
                "still_pending": still_pending,
                "failed": failed,
            },
        )
        await db.commit()

    return scanned


@celery_app.task(name="infinity_radius.reconcile_pending_collections")  # type: ignore[untyped-decorator]
def reconcile_pending_collections() -> int:
    return asyncio.run(_reconcile_pending_collections())
