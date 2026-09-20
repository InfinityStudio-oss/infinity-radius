"""Periodic retry of captive-portal access activation — the safety net for
a payment that was genuinely taken but whose access provisioning did not
complete.

Two states are picked up, and both matter:

  PENDING  activation was never attempted. The most likely cause is the
           process dying between the payment transaction committing and
           the activation transaction starting — precisely the window the
           payment/activation split creates on purpose.
  FAILED   activation was attempted and did not succeed, e.g. FreeRADIUS
           unreachable.

This task can only ever GRANT access. It never creates a payment, never
credits a wallet, never contacts a payment provider, and holds no Selcom
credentials — it does not import anything provider-shaped, exactly like
app/tasks/collections.py. Retrying is safe to the point of being boring:
every step it performs is idempotent (see app/services/captive_activation.py).

NOT SCHEDULED YET. No captive payment can reach a provider, so there is
nothing for this to find; it is registered so the recovery path exists and
is tested before the flow that needs it goes live. Adding it to
celery_app.conf.beat_schedule is a deliberate later step.
"""

import asyncio

import structlog

from app.core.celery_app import celery_app
from app.core.enums import ActivationStatus
from app.db.session import AsyncSessionLocal
from app.services.audit import write_audit_log
from app.services.captive_activation import (
    CaptivePortalActivationService,
    run_activation,
)

logger = structlog.get_logger("tasks.captive_activation")


async def _retry_pending_activations() -> int:
    scanned = 0
    activated = 0
    still_failing = 0

    async with AsyncSessionLocal() as db:
        transaction_ids = await CaptivePortalActivationService(db).list_retryable()
    scanned = len(transaction_ids)

    for transaction_id in transaction_ids:
        try:
            # Opens its own session per attempt, so one transaction's
            # failure can never affect another's — or the payments, which
            # were committed in entirely separate transactions already.
            result = await run_activation(transaction_id=transaction_id)
        except Exception:  # noqa: BLE001 — one bad row must not stop the sweep
            logger.exception(
                "captive_activation.retry_error", transaction_id=str(transaction_id)
            )
            still_failing += 1
            continue
        if result is ActivationStatus.ACTIVE:
            activated += 1
        else:
            still_failing += 1

    async with AsyncSessionLocal() as db:
        await write_audit_log(
            db,
            tenant_id=None,
            actor_id=None,
            action="captive_portal.activation_retry_swept",
            target_type=None,
            target_id=None,
            metadata={
                "scanned": scanned,
                "activated": activated,
                "still_failing": still_failing,
            },
        )
        await db.commit()

    logger.info(
        "captive_activation.retry_swept",
        scanned=scanned,
        activated=activated,
        still_failing=still_failing,
    )
    return scanned


@celery_app.task(name="infinity_radius.retry_captive_activations")  # type: ignore[untyped-decorator]
def retry_captive_activations() -> int:
    return asyncio.run(_retry_pending_activations())
