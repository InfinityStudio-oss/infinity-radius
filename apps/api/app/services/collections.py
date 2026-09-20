"""Selcom Mobile Checkout Collection orchestration — customer/subscriber
payments into a tenant's wallet via mobile-money STK push.

Flow: initiate_collection() creates a local Transaction row FIRST (status
CREATED, no provider contact yet), then calls Selcom's create-order-minimal
followed immediately by wallet-payment (the STK push) — see
app/integrations/selcom_collection/client.py. A successful wallet-payment
call only means Selcom ACCEPTED the request for processing (resultcode
111/"PENDING") — never that the customer paid.

The wallet is only ever credited by _apply_order_status(), always from a
value THIS process obtained itself via an authenticated GET
/v1/checkout/order-status call (a request we sign) — never from an inbound
webhook's own claims, which are only ever a SIGNAL to go query (see
process_webhook). This mirrors app/services/payouts.py's
"never trust an inbound callback's own claims" principle exactly, and the
real 2026-09-19 Disbursement incident (an unanticipated provider-amount
shape reaching a live payment) makes exact, no-tolerance amount matching
here non-negotiable from day one rather than something to discover live.
"""

import base64
import json
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import COLLECTION_TERMINAL_STATUSES, CollectionStatus, TransactionType
from app.core.errors import DomainValidationError, NotFoundError
from app.core.phone import normalize_tz_phone
from app.integrations.selcom_collection.client import SelcomCollectionClient
from app.integrations.selcom_collection.config import selcom_collection_config_from_settings
from app.integrations.selcom_collection.constants import (
    PAYMENT_STATUS_CANCELLED,
    PAYMENT_STATUS_COMPLETED,
    PAYMENT_STATUS_DECLINED_UNDOCUMENTED,
    PAYMENT_STATUS_EXPIRED_UNDOCUMENTED,
    PAYMENT_STATUS_FAILED_UNDOCUMENTED,
    PAYMENT_STATUS_INPROGRESS,
    PAYMENT_STATUS_PENDING,
    PAYMENT_STATUS_REJECTED,
    PAYMENT_STATUS_USERCANCELED_WEBHOOK_SPELLING,
    PAYMENT_STATUS_USERCANCELLED,
)
from app.integrations.selcom_collection.errors import (
    SelcomCollectionError,
    SelcomCollectionWebhookVerificationError,
)
from app.integrations.selcom_collection.schemas import OrderStatusData, WebhookPayload
from app.integrations.selcom_collection.signing import verify_webhook_request
from app.models.finance import Transaction
from app.repositories.customers import CustomerRepository
from app.repositories.finance import PaymentWebhookRepository, TransactionRepository
from app.services.audit import write_audit_log
from app.services.wallet import WalletService

logger = structlog.get_logger("services.collections")

_PAYMENT_STATUS_TO_COLLECTION_STATUS: dict[str, CollectionStatus] = {
    # Selcom-documented (order-status #get-order-status section).
    PAYMENT_STATUS_PENDING: CollectionStatus.PENDING,
    PAYMENT_STATUS_INPROGRESS: CollectionStatus.INPROGRESS,
    PAYMENT_STATUS_CANCELLED: CollectionStatus.CANCELLED,
    PAYMENT_STATUS_USERCANCELLED: CollectionStatus.USERCANCELLED,
    PAYMENT_STATUS_REJECTED: CollectionStatus.REJECTED,
    # Selcom-documented, but only in the #webhook-callback section's own
    # (differently-spelled) payment_status description — see constants.py.
    PAYMENT_STATUS_USERCANCELED_WEBHOOK_SPELLING: CollectionStatus.USERCANCELLED,
    # NOT part of Selcom's documented order-status enum — mapped
    # defensively only, see constants.py's PAYMENT_STATUS_*_UNDOCUMENTED
    # docstrings. If Selcom never actually sends these, this is inert.
    PAYMENT_STATUS_DECLINED_UNDOCUMENTED: CollectionStatus.DECLINED,
    PAYMENT_STATUS_FAILED_UNDOCUMENTED: CollectionStatus.FAILED,
    PAYMENT_STATUS_EXPIRED_UNDOCUMENTED: CollectionStatus.EXPIRED,
}

# The two mapped local targets that mean "still waiting" — the only ones
# eligible for the local stale-PENDING REQUIRES_REVIEW flag (see
# CollectionService._is_stale_pending). Every other mapped value above is
# already terminal and takes precedence unconditionally.
_NON_TERMINAL_MAPPED_TARGETS = frozenset({CollectionStatus.PENDING, CollectionStatus.INPROGRESS})


class CollectionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = TransactionRepository(db)
        self.customer_repo = CustomerRepository(db)
        self.wallet_service = WalletService(db)

    # ------------------------------------------------------------- helpers

    async def _transition(
        self,
        transaction: Transaction,
        *,
        to_status: CollectionStatus,
        actor_id: UUID | None,
        reason: str | None = None,
        audit_metadata: dict[str, object] | None = None,
        **extra_columns: object,
    ) -> None:
        await self.repo.update(transaction, status=to_status.value, **extra_columns)
        metadata: dict[str, object] = {"reason": reason} if reason else {}
        if audit_metadata:
            metadata.update(audit_metadata)
        await write_audit_log(
            self.db,
            tenant_id=transaction.tenant_id,
            actor_id=actor_id,
            action=f"collection.{to_status.value.lower()}",
            target_type="transaction",
            target_id=transaction.id,
            metadata=metadata or None,
        )

    async def _fail(
        self, transaction: Transaction, *, reason: str, actor_id: UUID | None
    ) -> None:
        await self._transition(
            transaction,
            to_status=CollectionStatus.FAILED,
            actor_id=actor_id,
            reason=reason,
            failed_at=datetime.now(UTC),
        )

    # -------------------------------------------------------- initiation

    async def initiate_collection(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        amount: Decimal,
        currency: str,
        phone: str,
        customer_id: UUID | None = None,
        description: str | None = None,
    ) -> Transaction:
        """Creates the local Transaction row, then Create Order Minimal,
        then the wallet-payment STK push — in that order, so a failure at
        any step leaves an honest, already-persisted FAILED record rather
        than nothing at all. Never sends a second STK for the same
        attempt: call this again only for a genuinely new attempt (a new
        Transaction row, a new order_id/transid) — see
        app/tasks/collections.py, which never calls this."""
        settings = get_settings()
        if not settings.selcom_collection_enabled:
            raise DomainValidationError("Selcom Collection is not enabled")
        if not settings.selcom_collection_production_enabled:
            raise DomainValidationError(
                "Selcom Collection production initiation is not enabled — the second "
                "kill switch (SELCOM_COLLECTION_PRODUCTION_ENABLED) is still off"
            )
        if currency != "TZS":
            raise DomainValidationError("Only TZS is supported for Collection at this time")
        if amount <= 0:
            raise DomainValidationError("amount must be positive")

        try:
            normalized_phone = normalize_tz_phone(phone)
        except ValueError as exc:
            raise DomainValidationError(str(exc)) from exc

        customer = None
        if customer_id is not None:
            customer = await self.customer_repo.get_by_id(tenant_id=tenant_id, id=customer_id)
            if customer is None:
                raise NotFoundError("Customer not found")

        buyer_name = (
            " ".join(part for part in (customer.first_name, customer.last_name) if part).strip()
            if customer
            else ""
        ) or normalized_phone
        buyer_email = (
            (customer.email if customer else None) or f"{normalized_phone}@customer.invalid"
        )

        # Globally unique by construction (not just per-tenant) — a
        # webhook must be able to find this row by reference alone,
        # before the tenant is known.
        reference = f"col-{uuid4().hex}"

        transaction = await self.repo.create(
            tenant_id=tenant_id,
            customer_id=customer_id,
            transaction_type=TransactionType.COLLECTION.value,
            reference=reference,
            amount=str(amount),
            currency=currency,
            status=CollectionStatus.CREATED.value,
            payer_phone=normalized_phone,
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="collection.created",
            target_type="transaction",
            target_id=transaction.id,
            metadata={"amount": str(amount)},
        )

        config = selcom_collection_config_from_settings()
        client = SelcomCollectionClient(config)

        webhook_b64 = None
        if settings.public_api_domain:
            webhook_url = (
                f"https://{settings.public_api_domain}{settings.api_v1_prefix}"
                "/webhooks/selcom-collection/checkout"
            )
            webhook_b64 = base64.b64encode(webhook_url.encode("utf-8")).decode("ascii")

        try:
            await client.create_order_minimal(
                order_id=reference,
                buyer_email=buyer_email,
                buyer_name=buyer_name,
                buyer_phone=normalized_phone,
                amount=amount,
                currency=currency,
                no_of_items=1,
                webhook_url_b64=webhook_b64,
                merchant_remarks=description,
            )
        except SelcomCollectionError as exc:
            logger.warning(
                "collections.create_order_failed",
                transaction_id=str(transaction.id),
                error=str(exc),
            )
            await self._fail(
                transaction, reason=f"Order creation failed: {exc}", actor_id=actor_id
            )
            return transaction

        transid = f"txn-{uuid4().hex}"
        try:
            wallet_response = await client.wallet_payment(
                transid=transid, order_id=reference, msisdn=normalized_phone
            )
        except SelcomCollectionError as exc:
            logger.warning(
                "collections.wallet_payment_failed",
                transaction_id=str(transaction.id),
                error=str(exc),
            )
            await self._fail(transaction, reason=f"STK request failed: {exc}", actor_id=actor_id)
            return transaction

        await self._transition(
            transaction,
            to_status=CollectionStatus.STK_SENT,
            actor_id=actor_id,
            reason=wallet_response.message,
            collection_transid=transid,
            stk_requested_at=datetime.now(UTC),
            provider_resultcode=wallet_response.resultcode,
            provider_message=wallet_response.message,
        )
        return transaction

    # ------------------------------------------------------- finalization

    def _is_stale_pending(self, transaction: Transaction) -> bool:
        """True once a still-PENDING/INPROGRESS order has outlived
        SELCOM_COLLECTION_PENDING_REVIEW_MINUTES since its STK was sent —
        an Infinity Radius operational threshold, never presented as a
        Selcom-documented timeout (Selcom's docs state none). <= 0
        disables this entirely."""
        threshold_minutes = get_settings().selcom_collection_pending_review_minutes
        if threshold_minutes <= 0 or transaction.stk_requested_at is None:
            return False
        elapsed = datetime.now(UTC) - transaction.stk_requested_at
        return elapsed >= timedelta(minutes=threshold_minutes)

    async def _apply_order_status(
        self,
        transaction: Transaction,
        *,
        status_data: OrderStatusData,
        actor_id: UUID | None,
        provider_resultcode: str | None = None,
    ) -> None:
        """The ONE place an authenticated order-status result is turned
        into a Transaction state change (and, on COMPLETED, a wallet
        credit) — reused by both the webhook path (which always queries
        first) and reconciliation, so there is exactly one amount/transid
        validation implementation, never duplicated.

        An explicit Selcom-mapped terminal status (CANCELLED/
        USERCANCELLED/REJECTED, plus the defensively-mapped DECLINED/
        FAILED/EXPIRED) always takes precedence and finalizes immediately,
        even over a transaction previously flagged REQUIRES_REVIEW —
        REQUIRES_REVIEW is only ever a waiting-room, never a status that
        blocks a later authoritative result."""
        if transaction.status in COLLECTION_TERMINAL_STATUSES:
            return  # already resolved — idempotent no-op

        payment_status = (status_data.payment_status or "").strip().upper()

        if payment_status == PAYMENT_STATUS_COMPLETED:
            # NOTE: order-status's `transid` is deliberately NOT compared
            # against transaction.collection_transid. They are different
            # identifiers by definition — Selcom documents the response
            # field as "Unique transaction identifier from the payment
            # channel", i.e. the mobile-money operator's own reference
            # (e.g. "DIK1X2R6BW"), whereas collection_transid is the id WE
            # generated and submitted to wallet-payment. An earlier
            # equality check between the two sent a genuinely COMPLETED
            # production payment to AMBIGUOUS (2026-09-19, TZS 1,000) and
            # would have done so for every successful payment. The
            # provider transid is evidence, stored below — never a
            # correlation key. order_id is the correlation key: we
            # generate it and Selcom echoes it back.
            if status_data.order_id and status_data.order_id != transaction.reference:
                await self._transition(
                    transaction,
                    to_status=CollectionStatus.AMBIGUOUS,
                    actor_id=actor_id,
                    reason=f"order_id mismatch: provider reported {status_data.order_id}",
                )
                return
            if status_data.amount is None or status_data.amount != Decimal(transaction.amount):
                await self._transition(
                    transaction,
                    to_status=CollectionStatus.AMBIGUOUS,
                    actor_id=actor_id,
                    reason=f"Amount mismatch: provider reported {status_data.amount}",
                )
                return
            # Defensive and currently inert: Selcom's documented order-status
            # response carries no currency field at all (see schemas.py), so
            # this only ever fires if one appears. Same skip-when-absent shape
            # as the transid/order_id checks above — an absent field is never
            # treated as a mismatch, and a present mismatch never credits.
            if status_data.currency and status_data.currency != transaction.currency:
                await self._transition(
                    transaction,
                    to_status=CollectionStatus.AMBIGUOUS,
                    actor_id=actor_id,
                    reason=f"Currency mismatch: provider reported {status_data.currency}",
                )
                return

            await self.wallet_service.process_collection(
                tenant_id=transaction.tenant_id,
                gross_amount=Decimal(transaction.amount),
                reference_type="selcom_collection",
                reference_id=transaction.id,
                description=f"Selcom Collection {status_data.reference or transaction.reference}",
            )
            # Provider-side evidence, in order of usefulness for support
            # and for reconciling against a payer's own mobile-money
            # statement: the payment channel's transid first (what the
            # customer sees on their SMS receipt), then Selcom Gateway's
            # own `reference`. Both are "Available on COMPLETED payments
            # only" per Selcom's docs, so either may be absent — absence is
            # never treated as a failure, since this is evidence, not a
            # financial control. transaction.collection_transid (ours) is
            # deliberately never written here and stays intact.
            await self._transition(
                transaction,
                to_status=CollectionStatus.COMPLETED,
                actor_id=actor_id,
                reason="Payment verified COMPLETED via authenticated order-status query",
                provider_reference=(
                    status_data.transid
                    or status_data.reference
                    or transaction.provider_reference
                ),
                channel=status_data.channel,
                provider_resultcode=provider_resultcode or "000",
                provider_message="COMPLETED",
                completed_at=datetime.now(UTC),
                audit_metadata={
                    "provider_channel_transid": status_data.transid,
                    "provider_gateway_reference": status_data.reference,
                    "local_request_transid": transaction.collection_transid,
                },
            )
            return

        mapped_status = _PAYMENT_STATUS_TO_COLLECTION_STATUS.get(payment_status)
        if mapped_status is None:
            # Unknown payment_status — never assumed safe, never credited,
            # never silently collapsed into PENDING.
            await self._transition(
                transaction,
                to_status=CollectionStatus.AMBIGUOUS,
                actor_id=actor_id,
                reason=f"Unrecognized payment_status: {status_data.payment_status!r}",
                provider_resultcode=provider_resultcode,
            )
            return

        if mapped_status not in _NON_TERMINAL_MAPPED_TARGETS:
            # An explicit Selcom-mapped terminal state always wins,
            # regardless of whether this transaction was previously
            # flagged REQUIRES_REVIEW.
            await self._transition(
                transaction,
                to_status=mapped_status,
                actor_id=actor_id,
                reason=f"Selcom order-status: {payment_status}",
                provider_message=payment_status,
                provider_resultcode=provider_resultcode,
                failed_at=datetime.now(UTC),
            )
            return

        # Still non-terminal per Selcom (PENDING/INPROGRESS-mapped).
        if transaction.status == CollectionStatus.REQUIRES_REVIEW.value:
            return  # already flagged — no-op, stays reconcilable, no audit spam

        if self._is_stale_pending(transaction):
            await self._transition(
                transaction,
                to_status=CollectionStatus.REQUIRES_REVIEW,
                actor_id=actor_id,
                reason=(
                    f"Provider order-status has remained {payment_status!r} past the local "
                    "SELCOM_COLLECTION_PENDING_REVIEW_MINUTES threshold — an Infinity Radius "
                    "operational flag for Super Admin/support visibility, never a Selcom-"
                    "reported status. Still fully reconcilable; a later genuine COMPLETED or "
                    "terminal result finalizes normally."
                ),
                provider_message=payment_status,
                provider_resultcode=provider_resultcode,
            )
            return

        await self._transition(
            transaction,
            to_status=mapped_status,
            actor_id=actor_id,
            reason=f"Selcom order-status: {payment_status}",
            provider_message=payment_status,
            provider_resultcode=provider_resultcode,
        )

    async def query_and_apply(self, *, transaction: Transaction, actor_id: UUID | None) -> None:
        """Queries Selcom's order-status for `transaction.reference` and
        applies whatever it authoritatively says. Assumes the caller
        already holds this transaction's row lock."""
        config = selcom_collection_config_from_settings()
        client = SelcomCollectionClient(config)
        try:
            response = await client.order_status(order_id=transaction.reference)
        except SelcomCollectionError as exc:
            logger.warning(
                "collections.order_status_query_failed",
                transaction_id=str(transaction.id),
                error=str(exc),
            )
            return
        # Sanitized (no secrets/signed headers) — the wrapper-level fields
        # a raw order-status response carries beyond the per-item data
        # Selcom docs describe as "Available on COMPLETED payments only"
        # for transid/channel/reference/msisdn; logged here since these
        # aren't persisted to a column for non-COMPLETED responses.
        logger.info(
            "collections.order_status_queried",
            transaction_id=str(transaction.id),
            resultcode=response.resultcode,
            result=response.result,
            message=response.message,
            payment_status=response.first.payment_status if response.first else None,
            # Both provider-side identifiers, kept distinct from our own
            # collection_transid — see _apply_order_status.
            provider_channel_transid=response.first.transid if response.first else None,
            provider_gateway_reference=response.first.reference if response.first else None,
        )
        if response.first is None:
            return
        await self._apply_order_status(
            transaction,
            status_data=response.first,
            actor_id=actor_id,
            provider_resultcode=response.resultcode,
        )

    async def reconcile(self, *, transaction_id: UUID) -> Transaction:
        """Public entry point for both the Super Admin-visible internal
        HMAC endpoint (worker-triggered) and any manual operator action —
        never called by a webhook directly (see process_webhook, which
        looks up by reference first)."""
        transaction = await self.repo.get_by_id_for_update(tenant_id=None, id=transaction_id)
        if transaction is None:
            raise NotFoundError("Collection transaction not found")
        await self.query_and_apply(transaction=transaction, actor_id=None)
        return transaction

    async def list_reconcilable_collections(self) -> list[Transaction]:
        """Every non-terminal Collection order a periodic sweep should
        query — pure DB read, no Selcom awareness, safe for the worker
        (see app/tasks/collections.py)."""
        non_terminal = [
            status.value
            for status in CollectionStatus
            if status not in COLLECTION_TERMINAL_STATUSES
        ]
        return await self.repo.list_by_statuses(statuses=non_terminal)

    # ----------------------------------------------------------- webhook

    async def process_webhook(
        self, *, headers: dict[str, str], body: bytes
    ) -> dict[str, str]:
        """Selcom's own docs: webhook only fires on successful
        transactions, and never signs amount/channel/phone — so this is
        used ONLY as a signal to go query order-status (an authenticated
        request we sign ourselves) before ever touching a wallet. See
        app/api/v1/webhooks.py for the route."""
        webhook_repo = PaymentWebhookRepository(self.db)
        try:
            parsed: object = json.loads(body) if body else {}
        except (ValueError, TypeError):
            parsed = None
        raw_payload: dict[str, Any] = (
            parsed
            if isinstance(parsed, dict)
            else {"_unparsable_body": body.decode("utf-8", errors="replace")}
        )

        config = selcom_collection_config_from_settings()
        signature_verified = False
        if config.is_configured:
            body_fields: OrderedDict[str, str] = OrderedDict(
                (k, str(v)) for k, v in raw_payload.items()
            )
            try:
                assert config.api_key is not None
                assert config.digest_method is not None
                verify_webhook_request(
                    api_key=config.api_key,
                    digest_method=config.digest_method,
                    api_secret=config.api_secret,
                    private_key_pem=config.private_key_pem,
                    headers=headers,
                    body_fields=body_fields,
                )
                signature_verified = True
            except SelcomCollectionWebhookVerificationError as exc:
                logger.warning("collections.webhook_verification_failed", detail=str(exc))

        webhook_row = await webhook_repo.create(
            tenant_id=None,
            provider="selcom_collection",
            payload=raw_payload,
            signature_verified=signature_verified,
            processed=False,
        )

        if not signature_verified:
            await webhook_repo.update(
                webhook_row, processed=True, processed_at=datetime.now(UTC)
            )
            return {"status": "rejected"}

        payload = WebhookPayload.model_validate(raw_payload)
        if not payload.order_id:
            await webhook_repo.update(
                webhook_row, processed=True, processed_at=datetime.now(UTC)
            )
            return {"status": "malformed"}

        transaction = await self.repo.get_by_reference_for_update(reference=payload.order_id)
        if transaction is None:
            await webhook_repo.update(
                webhook_row, processed=True, processed_at=datetime.now(UTC)
            )
            logger.warning("collections.webhook_unknown_order", order_id=payload.order_id)
            return {"status": "unknown_reference"}

        await webhook_repo.update(webhook_row, tenant_id=transaction.tenant_id)
        await write_audit_log(
            self.db,
            tenant_id=transaction.tenant_id,
            actor_id=None,
            action="collection.webhook_received",
            target_type="transaction",
            target_id=transaction.id,
        )
        await self.query_and_apply(transaction=transaction, actor_id=None)
        await webhook_repo.update(webhook_row, processed=True, processed_at=datetime.now(UTC))
        return {"status": "acknowledged"}
