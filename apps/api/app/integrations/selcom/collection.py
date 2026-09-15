"""Selcom Collection API integration — customer -> platform payments.

`initiate_collection()`/`query_collection()` call out to Selcom (not yet
implemented — see authentication.py/signatures.py; every path Selcom's
real endpoint/request format would need is a documented TODO, never a
guess).

`verify_callback()`/`process_callback()` handle Selcom's inbound webhook
(POST /api/v1/webhooks/selcom/collection — see app/api/v1/webhooks.py):
verify authenticity, validate the claim against our own Transaction
record, apply idempotency, and — only once genuinely verified — hand off
to the domain services that actually move a subscription from PENDING to
ACTIVE and record the payment (app.services.captive_portal.
CaptivePortalService.mark_transaction_completed).

Every "TODO(selcom-docs)" here marks something Anthropic has not been
given official Selcom documentation for. Nothing below invents an
endpoint path, an auth header, a signature format, or a callback field
name — see signatures.py and this module's `_extract_*` helpers, which
exist to show exactly where that mapping goes once it's confirmed, not to
guess it now.
"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.selcom.config import SelcomConfig
from app.integrations.selcom.exceptions import (
    SelcomAPIError,
    SelcomNotConfiguredError,
    SelcomNotImplementedError,
)
from app.integrations.selcom.schemas import (
    CollectionOrderRequest,
    CollectionOrderResponse,
    CollectionStatusResponse,
)
from app.integrations.selcom.signatures import verify_webhook_signature
from app.repositories.finance import PaymentWebhookRepository, TransactionRepository
from app.services.audit import write_audit_log

logger = structlog.get_logger("integrations.selcom.collection")

# Literal outcomes of one process_callback() call — never a raw bool, so
# every caller (webhook route, tests) can distinguish "nothing could be
# verified yet" from "verified but already handled" from "verified and
# just now applied".
CallbackOutcome = str  # "unverified" | "not_found" | "duplicate" | "failed" | "processed"


@dataclass(frozen=True)
class CallbackProcessingResult:
    status: CallbackOutcome
    detail: str | None = None


class CollectionService:
    def __init__(self, config: SelcomConfig) -> None:
        self._config = config

    async def initiate_collection(
        self, request: CollectionOrderRequest
    ) -> CollectionOrderResponse:
        """TODO(selcom-docs): POST to Selcom's real Collection order-
        creation endpoint. No endpoint path is invented here — this
        raises until the official integration guide supplies one, along
        with the request/response schema and authentication scheme."""
        if not self._config.is_configured:
            raise SelcomNotConfiguredError(
                "Selcom credentials are not configured. Set SELCOM_API_BASE_URL, "
                "SELCOM_API_KEY, SELCOM_API_SECRET, and SELCOM_MERCHANT_ID."
            )
        raise SelcomNotImplementedError(
            "Selcom Collection order creation is not implemented — awaiting official "
            "API documentation (endpoint path, request/response schema, auth scheme)."
        )

    async def query_collection(self, *, provider_reference: str) -> CollectionStatusResponse:
        """TODO(selcom-docs): GET Selcom's real order-status endpoint."""
        if not self._config.is_configured:
            raise SelcomNotConfiguredError(
                "Selcom credentials are not configured. Set SELCOM_API_BASE_URL, "
                "SELCOM_API_KEY, SELCOM_API_SECRET, and SELCOM_MERCHANT_ID."
            )
        raise SelcomNotImplementedError(
            "Selcom Collection status query is not implemented — awaiting official "
            "API documentation."
        )

    def verify_callback(self, *, headers: dict[str, str], body: bytes) -> bool:
        """Delegates to signatures.verify_webhook_signature — see that
        module for exactly what remains unknown. Raises
        SelcomNotConfiguredError/SelcomNotImplementedError until Selcom's
        real signing scheme is documented; never returns True on a guess."""
        return verify_webhook_signature(config=self._config, headers=headers, body=body)

    async def process_callback(
        self, db: AsyncSession, *, headers: dict[str, str], body: bytes
    ) -> CallbackProcessingResult:
        """The one entry point `POST /api/v1/webhooks/selcom/collection`
        calls. Always saves the raw event first (audit trail, regardless
        of outcome), then: verify -> validate reference/amount/state ->
        idempotency -> (only now) mark SUCCESS, activate the subscription,
        credit the wallet, sync RADIUS, write the audit log. Does not
        commit — the caller (the webhook route) does, exactly once, after
        this returns.
        """
        try:
            payload: dict[str, Any] = json.loads(body) if body else {}
        except (ValueError, TypeError):
            payload = {"_unparsable_body": body.decode("utf-8", errors="replace")}

        webhook_repo = PaymentWebhookRepository(db)
        webhook = await webhook_repo.create(
            tenant_id=None,
            provider="selcom",
            payload=payload,
            signature_verified=False,
            processed=False,
        )

        try:
            verified = self.verify_callback(headers=headers, body=body)
        except (SelcomNotConfiguredError, SelcomNotImplementedError) as exc:
            logger.warning("selcom.webhook.verification_unavailable", detail=str(exc))
            return CallbackProcessingResult(status="unverified", detail=str(exc))

        if not verified:
            # A real, attempted-and-failed verification — as opposed to
            # "we can't verify yet" above. Not reachable today (verify_callback
            # always raises first), but kept distinct for when it is.
            await webhook_repo.update(webhook, signature_verified=False, processed=True)
            return CallbackProcessingResult(status="unverified", detail="signature invalid")

        await webhook_repo.update(webhook, signature_verified=True)

        # --- Unreachable until verify_callback() above is a real check ---
        # TODO(selcom-docs): replace _extract_reference/_extract_amount/
        # _extract_provider_status with the real field names Selcom's
        # callback payload actually uses. Everything from here down
        # (idempotency, amount/state validation, activation, ledger,
        # RADIUS, audit) is real and already covered by tests that
        # simulate a verified callback.
        reference = self._extract_reference(payload)
        reported_amount = self._extract_amount(payload)
        provider_succeeded = self._extract_provider_status(payload)

        transaction_repo = TransactionRepository(db)
        transaction = await transaction_repo.get_by_reference(reference=reference)
        if transaction is None:
            await webhook_repo.update(webhook, processed=True, processed_at=datetime.now(UTC))
            return CallbackProcessingResult(status="not_found", detail=reference)

        await webhook_repo.update(webhook, tenant_id=transaction.tenant_id)

        if transaction.status != "pending":
            # Selcom may retry a webhook it didn't get a fast-enough ack
            # for — never re-apply activation/ledger/RADIUS for the same
            # transaction twice.
            await webhook_repo.update(webhook, processed=True, processed_at=datetime.now(UTC))
            return CallbackProcessingResult(status="duplicate")

        if Decimal(transaction.amount) != reported_amount:
            await webhook_repo.update(webhook, processed=True, processed_at=datetime.now(UTC))
            raise SelcomAPIError(
                f"Callback amount {reported_amount} does not match transaction amount "
                f"{transaction.amount} for reference {reference}",
                raw_response=payload,
            )

        if not provider_succeeded:
            await transaction_repo.update(transaction, status="failed")
            await write_audit_log(
                db,
                tenant_id=transaction.tenant_id,
                actor_id=None,
                action="captive_portal.payment_failed",
                target_type="transaction",
                target_id=transaction.id,
            )
            await webhook_repo.update(webhook, processed=True, processed_at=datetime.now(UTC))
            return CallbackProcessingResult(status="failed")

        # Import deferred to this call site to avoid a module-level import
        # cycle: app.services.captive_portal imports app.integrations.selcom
        # (to call initiate_collection), so this module can't import it back
        # at module scope.
        from app.services.captive_portal import CaptivePortalService

        await CaptivePortalService(db).mark_transaction_completed(transaction_id=transaction.id)
        await webhook_repo.update(webhook, processed=True, processed_at=datetime.now(UTC))
        return CallbackProcessingResult(status="processed")

    def _extract_reference(self, payload: dict[str, Any]) -> str:
        """TODO(selcom-docs): the real key carrying our reference back in
        Selcom's callback payload is unknown — this must not guess one."""
        raise SelcomNotImplementedError(
            "Extracting the transaction reference from a Selcom callback payload is "
            "not implemented — the real field name is unknown until official "
            "documentation confirms it."
        )

    def _extract_amount(self, payload: dict[str, Any]) -> Decimal:
        """TODO(selcom-docs): same as _extract_reference, for the amount field."""
        raise SelcomNotImplementedError(
            "Extracting the paid amount from a Selcom callback payload is not "
            "implemented — the real field name/format is unknown until official "
            "documentation confirms it."
        )

    def _extract_provider_status(self, payload: dict[str, Any]) -> bool:
        """TODO(selcom-docs): whatever Selcom's real success indicator is
        (a result code, a status string, ...) — never assume a specific
        value (e.g. "0000") means success without the official
        specification confirming it."""
        raise SelcomNotImplementedError(
            "Interpreting a Selcom callback's payment status is not implemented — "
            "the real success/failure indicator is unknown until official "
            "documentation confirms it."
        )
