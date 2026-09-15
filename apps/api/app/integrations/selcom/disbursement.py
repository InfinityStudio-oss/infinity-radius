"""Selcom Disbursement API integration — platform -> tenant payouts.

Mirrors collection.py's shape exactly: `initiate_disbursement()`/
`query_disbursement()` call out to Selcom (not yet implemented — see
authentication.py/signatures.py; every path Selcom's real endpoint/request
format would need is a documented TODO, never a guess).
`verify_callback()`/`process_callback()` handle Selcom's inbound
disbursement webhook (POST /api/v1/webhooks/selcom/disbursement — see
app/api/v1/webhooks.py): verify authenticity, validate the claim against
our own Withdrawal record, apply idempotency, and — only once genuinely
verified — hand off to PayoutService.apply_disbursement_result, which
actually moves reserved -> total_disbursed (or releases the reservation on
failure) and writes the DISBURSEMENT ledger entry.

The withdrawal-request/approval/2FA/maker-checker domain logic (a tenant
requesting a payout, which stays reserved against their wallet until
actually disbursed) lives in app/services/payouts.py — this module is only
the Selcom-facing adapter, and the whole disbursement flow additionally
requires Settings.selcom_disbursement_enabled (see app/core/config.py) —
a separate, explicit business/legal gate independent of whether Selcom
credentials happen to be configured.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.selcom.config import SelcomConfig
from app.integrations.selcom.exceptions import SelcomNotConfiguredError, SelcomNotImplementedError
from app.integrations.selcom.schemas import (
    DisbursementOrderRequest,
    DisbursementOrderResponse,
    DisbursementStatusResponse,
)
from app.integrations.selcom.signatures import verify_webhook_signature
from app.repositories.finance import PaymentWebhookRepository, WithdrawalRepository

logger = structlog.get_logger("integrations.selcom.disbursement")

# Same outcome vocabulary as CollectionService.process_callback — never a
# raw bool, so every caller can distinguish "nothing could be verified
# yet" from "verified but already handled" from "verified and just now applied".
CallbackOutcome = str  # "unverified" | "not_found" | "duplicate" | "failed" | "processed"


@dataclass(frozen=True)
class CallbackProcessingResult:
    status: CallbackOutcome
    detail: str | None = None


class SelcomDisbursementService:
    def __init__(self, config: SelcomConfig) -> None:
        self._config = config

    async def initiate_disbursement(
        self, request: DisbursementOrderRequest
    ) -> DisbursementOrderResponse:
        """TODO(selcom-docs): POST to Selcom's real Disbursement order-
        creation endpoint. No endpoint path is invented here — this raises
        until the official integration guide supplies one, along with the
        request/response schema and authentication scheme."""
        if not self._config.is_configured:
            raise SelcomNotConfiguredError(
                "Selcom credentials are not configured. Set SELCOM_API_BASE_URL, "
                "SELCOM_API_KEY, SELCOM_API_SECRET, and SELCOM_MERCHANT_ID."
            )
        raise SelcomNotImplementedError(
            "Selcom Disbursement order creation is not implemented — awaiting "
            "official API documentation (endpoint path, request/response schema, "
            "auth scheme)."
        )

    async def query_disbursement(self, *, provider_reference: str) -> DisbursementStatusResponse:
        """TODO(selcom-docs): GET Selcom's real disbursement-status endpoint."""
        if not self._config.is_configured:
            raise SelcomNotConfiguredError(
                "Selcom credentials are not configured. Set SELCOM_API_BASE_URL, "
                "SELCOM_API_KEY, SELCOM_API_SECRET, and SELCOM_MERCHANT_ID."
            )
        raise SelcomNotImplementedError(
            "Selcom Disbursement status query is not implemented — awaiting "
            "official API documentation."
        )

    def verify_callback(self, *, headers: dict[str, str], body: bytes) -> bool:
        """Delegates to the same signatures.verify_webhook_signature used
        by collection callbacks — Selcom's real signing scheme, once
        documented, presumably applies to both. Raises
        SelcomNotConfiguredError/SelcomNotImplementedError until then;
        never returns True on a guess."""
        return verify_webhook_signature(config=self._config, headers=headers, body=body)

    async def process_callback(
        self, db: AsyncSession, *, headers: dict[str, str], body: bytes
    ) -> CallbackProcessingResult:
        """The one entry point `POST /api/v1/webhooks/selcom/disbursement`
        calls. Always saves the raw event first (audit trail, regardless
        of outcome), then: verify -> find the withdrawal by provider
        reference -> idempotency -> (only now) apply the result via
        PayoutService.apply_disbursement_result. Does not commit — the
        caller (the webhook route) does, exactly once, after this returns.
        """
        try:
            payload: dict[str, Any] = json.loads(body) if body else {}
        except (ValueError, TypeError):
            payload = {"_unparsable_body": body.decode("utf-8", errors="replace")}

        webhook_repo = PaymentWebhookRepository(db)
        webhook = await webhook_repo.create(
            tenant_id=None,
            provider="selcom_disbursement",
            payload=payload,
            signature_verified=False,
            processed=False,
        )

        try:
            verified = self.verify_callback(headers=headers, body=body)
        except (SelcomNotConfiguredError, SelcomNotImplementedError) as exc:
            logger.warning("selcom.disbursement_webhook.verification_unavailable", detail=str(exc))
            return CallbackProcessingResult(status="unverified", detail=str(exc))

        if not verified:
            # A real, attempted-and-failed verification — as opposed to
            # "we can't verify yet" above. Not reachable today (verify_callback
            # always raises first), but kept distinct for when it is.
            await webhook_repo.update(webhook, signature_verified=False, processed=True)
            return CallbackProcessingResult(status="unverified", detail="signature invalid")

        await webhook_repo.update(webhook, signature_verified=True)

        # --- Unreachable until verify_callback() above is a real check ---
        # TODO(selcom-docs): replace _extract_provider_reference/_extract_status
        # with the real field names Selcom's disbursement callback payload
        # actually uses. Everything from here down (idempotency, lookup,
        # ledger, audit) is real and already covered by tests that simulate
        # a verified callback.
        provider_reference = self._extract_provider_reference(payload)
        provider_succeeded = self._extract_status(payload)

        withdrawal_repo = WithdrawalRepository(db)
        withdrawal = await withdrawal_repo.get_by_provider_reference(
            provider_reference=provider_reference
        )
        if withdrawal is None:
            await webhook_repo.update(webhook, processed=True, processed_at=datetime.now(UTC))
            return CallbackProcessingResult(status="not_found", detail=provider_reference)

        await webhook_repo.update(webhook, tenant_id=withdrawal.tenant_id)

        # Import deferred to this call site to avoid a module-level import
        # cycle: app.services.payouts imports app.integrations.selcom (to
        # call initiate_disbursement), so this module can't import it back
        # at module scope.
        from app.services.payouts import PayoutService

        if withdrawal.status != "PROCESSING":
            # Selcom may retry a callback it didn't get a fast-enough ack
            # for — never re-apply the ledger effect for the same
            # withdrawal twice. PayoutService.apply_disbursement_result
            # enforces this same guard independently.
            await webhook_repo.update(webhook, processed=True, processed_at=datetime.now(UTC))
            return CallbackProcessingResult(status="duplicate")

        await PayoutService(db).apply_disbursement_result(
            withdrawal_id=withdrawal.id,
            provider_succeeded=provider_succeeded,
            provider_reference=provider_reference,
            detail=json.dumps(payload) if not provider_succeeded else None,
        )
        await webhook_repo.update(webhook, processed=True, processed_at=datetime.now(UTC))
        return CallbackProcessingResult(status="processed")

    def _extract_provider_reference(self, payload: dict[str, Any]) -> str:
        """TODO(selcom-docs): the real key carrying Selcom's own
        disbursement order reference in the callback payload is unknown —
        this must not guess one."""
        raise SelcomNotImplementedError(
            "Extracting the provider reference from a Selcom disbursement callback "
            "payload is not implemented — the real field name is unknown until "
            "official documentation confirms it."
        )

    def _extract_status(self, payload: dict[str, Any]) -> bool:
        """TODO(selcom-docs): whatever Selcom's real success indicator is
        for a disbursement callback — never assume a specific value means
        success without the official specification confirming it."""
        raise SelcomNotImplementedError(
            "Interpreting a Selcom disbursement callback's status is not "
            "implemented — the real success/failure indicator is unknown until "
            "official documentation confirms it."
        )
