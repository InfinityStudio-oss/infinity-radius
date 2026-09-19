"""External payment-provider webhooks. No Supabase auth here — these are
called by the provider's own servers, not our frontend — authenticity is
established by verifying the provider's own request signature instead
(app.integrations.selcom.signatures, currently a documented TODO pending
Selcom's official API documentation). Until that exists, every inbound
callback is saved (audit trail) but never acted on — see
app.integrations.selcom.collection.CollectionService.process_callback.
"""

import contextlib
import json
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.db.session import get_db
from app.integrations.selcom.collection import CollectionService
from app.integrations.selcom.disbursement import SelcomDisbursementService
from app.integrations.selcom.exceptions import SelcomAPIError, SelcomWebhookVerificationError
from app.repositories.finance import PaymentWebhookRepository, WithdrawalRepository
from app.services.captive_portal import selcom_config_from_settings
from app.services.payouts import PayoutService

logger = structlog.get_logger("webhooks.selcom")

router = APIRouter()


@router.post("/selcom/collection")
async def selcom_collection_webhook(
    request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    body = await request.body()
    headers = dict(request.headers)

    service = CollectionService(selcom_config_from_settings())

    try:
        result = await service.process_callback(db, headers=headers, body=body)
    except SelcomWebhookVerificationError as exc:
        await db.rollback()
        logger.warning("selcom.webhook.verification_failed", detail=str(exc))
        # 200 on purpose even on rejection: Selcom's retry behavior on a
        # non-2xx response isn't documented, and this must never let a
        # forged retry distinguish "signature rejected" from any other
        # outcome via the HTTP status code alone.
        return {"status": "rejected"}
    except SelcomAPIError as exc:
        await db.rollback()
        logger.error("selcom.webhook.processing_error", detail=str(exc))
        return {"status": "error"}

    await db.commit()
    return {"status": result.status}


@router.api_route("/selcom-business/disbursement", methods=["GET", "HEAD"])
async def selcom_business_disbursement_webhook_reachability_check() -> dict[str, str]:
    """Selcom's own portal probes the configured callback URL (GET and/or
    HEAD — not documented which, so both are handled explicitly; Starlette
    does not auto-add HEAD to a plain @router.get route) before accepting
    it as "verified" — a separate check from the real callback delivery,
    which is always POST (see below) and does the actual work. This does
    nothing but confirm the URL resolves to a live 200 — no auth, no
    processing, no real callback ever arrives this way."""
    return {"status": "ok"}


@router.post("/selcom-business/disbursement")
async def selcom_business_disbursement_webhook(
    request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    """Selcom Business's disbursement callback — developer.selcom.business
    documents no signature/authentication scheme for it, so this is used
    only as a SIGNAL to query, never trusted to move money on its own
    claims (see app/services/payouts.py.reconcile_withdrawal, which
    re-verifies via an authenticated GET /v1/transaction/query before
    ever finalizing anything). Always saves the raw callback first,
    regardless of whether a matching withdrawal is ever found."""
    body = await request.body()
    try:
        payload: dict[str, Any] = json.loads(body) if body else {}
    except (ValueError, TypeError):
        payload = {"_unparsable_body": body.decode("utf-8", errors="replace")}

    webhook_repo = PaymentWebhookRepository(db)
    webhook = await webhook_repo.create(
        tenant_id=None,
        provider="selcom_business_disbursement",
        payload=payload,
        signature_verified=False,
        processed=False,
    )

    reference_id = payload.get("reference_id")
    if not isinstance(reference_id, str) or not reference_id:
        await webhook_repo.update(webhook, processed=True, processed_at=datetime.now(UTC))
        await db.commit()
        logger.warning("selcom_business.disbursement_webhook.malformed")
        return {"status": "malformed"}

    withdrawal_repo = WithdrawalRepository(db)
    withdrawal = await withdrawal_repo.get_by_idempotency_key(
        idempotency_key=reference_id
    ) or await withdrawal_repo.get_by_provider_reference(provider_reference=reference_id)
    if withdrawal is None:
        await webhook_repo.update(webhook, processed=True, processed_at=datetime.now(UTC))
        await db.commit()
        logger.warning("selcom_business.disbursement_webhook.unknown_reference")
        return {"status": "unknown_reference"}

    await webhook_repo.update(webhook, tenant_id=withdrawal.tenant_id)

    with contextlib.suppress(NotFoundError):
        await PayoutService(db).reconcile_withdrawal(withdrawal_id=withdrawal.id)
    await webhook_repo.update(webhook, processed=True, processed_at=datetime.now(UTC))
    await db.commit()
    return {"status": "acknowledged"}


@router.post("/selcom/disbursement")
async def selcom_disbursement_webhook(
    request: Request, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    """Mirrors selcom_collection_webhook exactly — see
    app.integrations.selcom.disbursement.SelcomDisbursementService.process_callback
    for what's real vs. still TODO(selcom-docs). Feature-flagged: this
    route always saves the raw callback (audit trail) regardless of
    Settings.selcom_disbursement_enabled — the flag only gates whether
    Infinity Radius ever submits a disbursement, not whether an inbound
    callback (which Selcom could still send unprompted) gets recorded."""
    body = await request.body()
    headers = dict(request.headers)

    service = SelcomDisbursementService(selcom_config_from_settings())

    try:
        result = await service.process_callback(db, headers=headers, body=body)
    except SelcomWebhookVerificationError as exc:
        await db.rollback()
        logger.warning("selcom.disbursement_webhook.verification_failed", detail=str(exc))
        return {"status": "rejected"}
    except SelcomAPIError as exc:
        await db.rollback()
        logger.error("selcom.disbursement_webhook.processing_error", detail=str(exc))
        return {"status": "error"}

    await db.commit()
    return {"status": result.status}
