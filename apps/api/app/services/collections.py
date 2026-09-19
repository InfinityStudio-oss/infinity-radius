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
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import COLLECTION_TERMINAL_STATUSES, CollectionStatus
from app.core.errors import DomainValidationError, NotFoundError
from app.core.phone import normalize_tz_phone
from app.integrations.selcom_collection.client import SelcomCollectionClient
from app.integrations.selcom_collection.config import selcom_collection_config_from_settings
from app.integrations.selcom_collection.constants import (
    PAYMENT_STATUS_CANCELLED,
    PAYMENT_STATUS_COMPLETED,
    PAYMENT_STATUS_INPROGRESS,
    PAYMENT_STATUS_PENDING,
    PAYMENT_STATUS_REJECTED,
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
    PAYMENT_STATUS_PENDING: CollectionStatus.PENDING,
    PAYMENT_STATUS_INPROGRESS: CollectionStatus.INPROGRESS,
    PAYMENT_STATUS_CANCELLED: CollectionStatus.CANCELLED,
    PAYMENT_STATUS_USERCANCELLED: CollectionStatus.USERCANCELLED,
    PAYMENT_STATUS_REJECTED: CollectionStatus.REJECTED,
}


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

    async def _apply_order_status(
        self, transaction: Transaction, *, status_data: OrderStatusData, actor_id: UUID | None
    ) -> None:
        """The ONE place an authenticated order-status result is turned
        into a Transaction state change (and, on COMPLETED, a wallet
        credit) — reused by both the webhook path (which always queries
        first) and reconciliation, so there is exactly one amount/transid
        validation implementation, never duplicated."""
        if transaction.status in COLLECTION_TERMINAL_STATUSES:
            return  # already resolved — idempotent no-op

        payment_status = (status_data.payment_status or "").strip().upper()

        if payment_status == PAYMENT_STATUS_COMPLETED:
            if (
                transaction.collection_transid
                and status_data.transid
                and status_data.transid != transaction.collection_transid
            ):
                await self._transition(
                    transaction,
                    to_status=CollectionStatus.AMBIGUOUS,
                    actor_id=actor_id,
                    reason=f"transid mismatch: provider reported {status_data.transid}",
                )
                return
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

            await self.wallet_service.process_collection(
                tenant_id=transaction.tenant_id,
                gross_amount=Decimal(transaction.amount),
                reference_type="selcom_collection",
                reference_id=transaction.id,
                description=f"Selcom Collection {status_data.reference or transaction.reference}",
            )
            await self._transition(
                transaction,
                to_status=CollectionStatus.COMPLETED,
                actor_id=actor_id,
                reason="Payment verified COMPLETED via authenticated order-status query",
                provider_reference=status_data.reference or transaction.provider_reference,
                channel=status_data.channel,
                provider_resultcode="000",
                provider_message="COMPLETED",
                completed_at=datetime.now(UTC),
            )
            return

        if payment_status in _PAYMENT_STATUS_TO_COLLECTION_STATUS:
            new_status = _PAYMENT_STATUS_TO_COLLECTION_STATUS[payment_status]
            is_terminal = new_status in COLLECTION_TERMINAL_STATUSES
            await self._transition(
                transaction,
                to_status=new_status,
                actor_id=actor_id,
                reason=f"Selcom order-status: {payment_status}",
                provider_message=payment_status,
                failed_at=datetime.now(UTC) if is_terminal else None,
            )
            return

        # Unknown payment_status — never assumed safe, never credited.
        await self._transition(
            transaction,
            to_status=CollectionStatus.AMBIGUOUS,
            actor_id=actor_id,
            reason=f"Unrecognized payment_status: {status_data.payment_status!r}",
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
        if response.first is None:
            return
        await self._apply_order_status(transaction, status_data=response.first, actor_id=actor_id)

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
