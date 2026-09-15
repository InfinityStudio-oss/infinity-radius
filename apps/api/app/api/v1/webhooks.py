"""External payment-provider webhooks. No Supabase auth here — these are
called by the provider's own servers, not our frontend — authenticity is
established by verifying the provider's own request signature instead
(app.integrations.selcom.signatures, currently a documented TODO pending
Selcom's official API documentation). Until that exists, every inbound
callback is saved (audit trail) but never acted on — see
app.integrations.selcom.collection.CollectionService.process_callback.
"""

import structlog
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.integrations.selcom.collection import CollectionService
from app.integrations.selcom.disbursement import SelcomDisbursementService
from app.integrations.selcom.exceptions import SelcomAPIError, SelcomWebhookVerificationError
from app.services.captive_portal import selcom_config_from_settings

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
