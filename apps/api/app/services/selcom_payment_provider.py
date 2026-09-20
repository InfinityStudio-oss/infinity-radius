"""Provider-generic Selcom Mobile Checkout orchestration.

Everything in this module is about talking to Selcom and turning an
AUTHENTICATED order-status result into a Transaction state change. It
deliberately knows nothing about WHICH business flow a payment belongs
to — that is `transactions.transaction_type`, supplied by the caller via
`SelcomPaymentFlow`, and what happens once a payment is verified, which
is supplied as `finalize_payment`.

Two flows are expected to use this:
  - the tenant-facing Collection dashboard (app/services/collections.py),
    validated end-to-end on real production payments;
  - captive-portal package payments (app/services/captive_portal.py),
    NOT yet wired up — see docs/architecture.md.

The split exists so the second one cannot drift from the first. Every
financial control that made Collection safe lives here, once:

  - the wallet is only ever credited from a value THIS process obtained
    itself via a signed GET /v1/checkout/order-status — never from an
    inbound webhook's own claims (see process_webhook, which only ever
    uses a webhook as a SIGNAL to go query);
  - exact, no-tolerance order_id/amount/currency matching before any
    finalization, after the real 2026-09-19 Disbursement incident;
  - the provider/channel `transid` is evidence only, never a correlation
    key and never compared against our own `collection_transid` (an
    earlier equality check between the two sent a genuinely COMPLETED
    production payment to AMBIGUOUS);
  - an already-terminal transaction is an idempotent no-op, so a
    duplicate COMPLETED can never credit twice;
  - nothing here ever re-sends a wallet-payment/STK or creates a second
    order for an existing attempt.
"""

import base64
import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import (
    COLLECTION_TERMINAL_STATUSES,
    CollectionStatus,
    PaymentProvider,
    TransactionType,
)
from app.core.errors import NotFoundError
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
from app.repositories.finance import PaymentWebhookRepository, TransactionRepository
from app.services.audit import write_audit_log

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
# SelcomPaymentProvider._is_stale_pending). Every other mapped value above
# is already terminal and takes precedence unconditionally.
_NON_TERMINAL_MAPPED_TARGETS = frozenset({CollectionStatus.PENDING, CollectionStatus.INPROGRESS})


class SelcomPaymentFlowMismatchError(Exception):
    """A transaction was about to be finalized by a flow that doesn't own
    it — see the 2026-09-20 production incident.

    A CAPTIVE_PORTAL payment was reconciled through CollectionService's
    own provider (COLLECTION_FLOW). The wallet was credited correctly
    (both flows' finalizers call the identical WalletService.
    process_collection), but activation_status was never set, because
    CollectionService's finalizer has no notion of activation — and once
    a transaction reaches a terminal status, apply_order_status's own
    idempotency guard means it can never be finalized again by anyone,
    correct flow included. The money was safe; the customer's access was
    silently never provisioned.

    This is raised by apply_order_status as a hard backstop, and is not
    expected to be reachable in normal operation: query_and_apply/
    reconcile/process_webhook all resolve the correct flow via
    SelcomPaymentProvider._provider_for before ever calling
    apply_order_status on a transaction they don't own.
    """


@dataclass(frozen=True)
class SelcomPaymentFlow:
    """The ONLY things that differ between two Selcom-backed payment
    families. Everything else — signing, order creation, the STK push,
    the order-status state machine, webhook handling — is shared.

    `transaction_type` is the authoritative `transactions.transaction_type`
    discriminator (see the a762b365749e migration): the business flow a
    row belongs to, deliberately independent of which provider processed
    it. A captive-portal payment stays CAPTIVE_PORTAL even though Selcom
    Collection is the provider.

    `payment_provider` is the OTHER half of that pair: which provider
    actually settles the money. Reconciliation discovers work by this,
    never by transaction_type, so a Selcom-settled captive-portal payment
    is swept exactly like a tenant Collection while a future voucher/cash
    flow is never sent to Selcom's order-status at all.

    `audit_namespace`/`log_namespace` keep each flow's audit actions and
    structured log events distinguishable after the fact.
    """

    transaction_type: TransactionType
    payment_provider: PaymentProvider
    reference_prefix: str
    audit_namespace: str
    log_namespace: str


# Ledger/entitlement work to run once — and only once — a payment has been
# verified COMPLETED by an authenticated order-status query. Runs inside the
# same row-locked transaction as the COMPLETED transition, so a failure here
# rolls the transition back rather than leaving a credited-but-not-COMPLETED
# row behind.
PaymentFinalizer = Callable[[Transaction, OrderStatusData], Awaitable[None]]


class SelcomPaymentProvider:
    """One Selcom Mobile Checkout payment family's provider interactions.

    Construct with the flow it serves and what to do on verified payment;
    it never decides either for itself.
    """

    def __init__(
        self,
        db: AsyncSession,
        *,
        flow: SelcomPaymentFlow,
        finalize_payment: PaymentFinalizer,
    ) -> None:
        self.db = db
        self.repo = TransactionRepository(db)
        self._flow = flow
        self._finalize_payment = finalize_payment
        self._logger = structlog.get_logger(f"services.{flow.log_namespace}")

    # ------------------------------------------------------------- helpers

    def new_reference(self) -> str:
        """OUR order_id, sent to create-order-minimal and echoed back by
        Selcom — the one correlation key. Globally unique by construction
        (not just per-tenant): a webhook must be able to find its row by
        reference alone, before the tenant is known."""
        return f"{self._flow.reference_prefix}{uuid4().hex}"

    async def transition(
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
            action=f"{self._flow.audit_namespace}.{to_status.value.lower()}",
            target_type="transaction",
            target_id=transaction.id,
            metadata=metadata or None,
        )

    async def fail(self, transaction: Transaction, *, reason: str, actor_id: UUID | None) -> None:
        await self.transition(
            transaction,
            to_status=CollectionStatus.FAILED,
            actor_id=actor_id,
            reason=reason,
            failed_at=datetime.now(UTC),
        )

    # -------------------------------------------------------- initiation

    async def create_order_and_send_stk(
        self,
        transaction: Transaction,
        *,
        actor_id: UUID | None,
        buyer_name: str,
        buyer_email: str,
        msisdn: str,
        amount: Decimal,
        currency: str,
        description: str | None = None,
    ) -> Transaction:
        """Create Order Minimal, then the wallet-payment STK push — in
        that order, against an ALREADY-PERSISTED transaction row, so a
        failure at either step leaves an honest FAILED record rather than
        nothing at all.

        Never sends a second STK for the same attempt: a genuinely new
        customer attempt gets a new row with a new order_id/transid. The
        caller is responsible for the kill-switch gates BEFORE this is
        reached — this method assumes it is already cleared to contact
        Selcom.
        """
        settings = get_settings()
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
                order_id=transaction.reference,
                buyer_email=buyer_email,
                buyer_name=buyer_name,
                buyer_phone=msisdn,
                amount=amount,
                currency=currency,
                no_of_items=1,
                webhook_url_b64=webhook_b64,
                merchant_remarks=description,
            )
        except SelcomCollectionError as exc:
            self._logger.warning(
                f"{self._flow.log_namespace}.create_order_failed",
                transaction_id=str(transaction.id),
                error=str(exc),
                status_code=getattr(exc, "status_code", None),
                # Selcom's own response body — the exact evidence needed
                # to tell an application-level rejection (bad field,
                # unauthorized vendor, ...) apart from a transport/edge
                # block, which was missing entirely during the
                # 2026-09-20 captive 403 investigation: the exception
                # carried it, but nothing ever logged it, so it was lost
                # the moment the request finished. Selcom's own error
                # response never contains our secrets.
                provider_response=getattr(exc, "raw_response", None),
            )
            await self.fail(transaction, reason=f"Order creation failed: {exc}", actor_id=actor_id)
            return transaction

        transid = f"txn-{uuid4().hex}"
        try:
            wallet_response = await client.wallet_payment(
                transid=transid, order_id=transaction.reference, msisdn=msisdn
            )
        except SelcomCollectionError as exc:
            self._logger.warning(
                f"{self._flow.log_namespace}.wallet_payment_failed",
                transaction_id=str(transaction.id),
                error=str(exc),
                status_code=getattr(exc, "status_code", None),
                provider_response=getattr(exc, "raw_response", None),
            )
            await self.fail(transaction, reason=f"STK request failed: {exc}", actor_id=actor_id)
            return transaction

        await self.transition(
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

    async def apply_order_status(
        self,
        transaction: Transaction,
        *,
        status_data: OrderStatusData,
        actor_id: UUID | None,
        provider_resultcode: str | None = None,
    ) -> None:
        """The ONE place an authenticated order-status result is turned
        into a Transaction state change (and, on COMPLETED, the flow's own
        finalization) — reused by both the webhook path (which always
        queries first) and reconciliation, so there is exactly one
        amount/order_id validation implementation, never duplicated.

        An explicit Selcom-mapped terminal status (CANCELLED/
        USERCANCELLED/REJECTED, plus the defensively-mapped DECLINED/
        FAILED/EXPIRED) always takes precedence and finalizes immediately,
        even over a transaction previously flagged REQUIRES_REVIEW —
        REQUIRES_REVIEW is only ever a waiting-room, never a status that
        blocks a later authoritative result."""
        if transaction.transaction_type != self._flow.transaction_type.value:
            # Hard backstop, not expected to fire in normal operation —
            # see SelcomPaymentFlowMismatchError. Checked BEFORE the
            # terminal-status no-op below on purpose: a mismatched flow
            # must never even reach the "already resolved" branch, or a
            # caller could mistake a loud rejection for a quiet success.
            raise SelcomPaymentFlowMismatchError(
                f"{self._flow.log_namespace} cannot finalize transaction {transaction.id} "
                f"(transaction_type={transaction.transaction_type!r}, "
                f"expected {self._flow.transaction_type.value!r})"
            )
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
                await self.transition(
                    transaction,
                    to_status=CollectionStatus.AMBIGUOUS,
                    actor_id=actor_id,
                    reason=f"order_id mismatch: provider reported {status_data.order_id}",
                )
                return
            if status_data.amount is None or status_data.amount != Decimal(transaction.amount):
                await self.transition(
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
                await self.transition(
                    transaction,
                    to_status=CollectionStatus.AMBIGUOUS,
                    actor_id=actor_id,
                    reason=f"Currency mismatch: provider reported {status_data.currency}",
                )
                return

            await self._finalize_payment(transaction, status_data)
            # Provider-side evidence, in order of usefulness for support
            # and for reconciling against a payer's own mobile-money
            # statement: the payment channel's transid first (what the
            # customer sees on their SMS receipt), then Selcom Gateway's
            # own `reference`. Both are "Available on COMPLETED payments
            # only" per Selcom's docs, so either may be absent — absence is
            # never treated as a failure, since this is evidence, not a
            # financial control. transaction.collection_transid (ours) is
            # deliberately never written here and stays intact.
            await self.transition(
                transaction,
                to_status=CollectionStatus.COMPLETED,
                actor_id=actor_id,
                reason="Payment verified COMPLETED via authenticated order-status query",
                provider_reference=(
                    status_data.transid or status_data.reference or transaction.provider_reference
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
            await self.transition(
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
            await self.transition(
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
            await self.transition(
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

        await self.transition(
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
            self._logger.warning(
                f"{self._flow.log_namespace}.order_status_query_failed",
                transaction_id=str(transaction.id),
                error=str(exc),
            )
            return
        # Sanitized (no secrets/signed headers) — the wrapper-level fields
        # a raw order-status response carries beyond the per-item data
        # Selcom docs describe as "Available on COMPLETED payments only"
        # for transid/channel/reference/msisdn; logged here since these
        # aren't persisted to a column for non-COMPLETED responses.
        self._logger.info(
            f"{self._flow.log_namespace}.order_status_queried",
            transaction_id=str(transaction.id),
            resultcode=response.resultcode,
            result=response.result,
            message=response.message,
            payment_status=response.first.payment_status if response.first else None,
            # Both provider-side identifiers, kept distinct from our own
            # collection_transid — see apply_order_status.
            provider_channel_transid=response.first.transid if response.first else None,
            provider_gateway_reference=response.first.reference if response.first else None,
        )
        if response.first is None:
            return
        await self.apply_order_status(
            transaction,
            status_data=response.first,
            actor_id=actor_id,
            provider_resultcode=response.resultcode,
        )

    def _provider_for(self, transaction: Transaction) -> "SelcomPaymentProvider":
        """Returns the provider that actually owns `transaction`'s flow —
        `self` if it already matches, otherwise the correct sibling
        flow's provider on the SAME db session.

        Exists because the shared webhook and the payment_provider-scoped
        reconciliation sweep both discover transactions ACROSS flow
        boundaries by design (see list_reconcilable): the flow whose code
        happens to receive a transaction_id/order_id is not necessarily
        the flow that created it. See the 2026-09-20 incident this fixes,
        and SelcomPaymentFlowMismatchError for what happens if this is
        ever bypassed.

        Deferred imports: both flow modules import THIS one (they
        construct a SelcomPaymentProvider), so importing them at module
        scope here would be circular.
        """
        if transaction.transaction_type == self._flow.transaction_type.value:
            return self
        if transaction.transaction_type == TransactionType.COLLECTION.value:
            from app.services.collections import CollectionService

            return CollectionService(self.db).provider
        if transaction.transaction_type == TransactionType.CAPTIVE_PORTAL.value:
            from app.services.captive_portal import CaptivePortalService

            return CaptivePortalService(self.db).provider
        raise SelcomPaymentFlowMismatchError(
            f"No Selcom payment flow is registered for transaction_type="
            f"{transaction.transaction_type!r} (transaction {transaction.id})"
        )

    async def reconcile(self, *, transaction_id: UUID) -> Transaction:
        """Public entry point for both the Super Admin-visible internal
        HMAC endpoint (worker-triggered) and any manual operator action —
        never called by a webhook directly (see process_webhook, which
        looks up by reference first).

        Dispatches to the transaction's OWN flow via _provider_for before
        finalizing — this is what makes it safe for the payment_provider-
        scoped reconciliation sweep to call this on a transaction_id it
        discovered without knowing (or needing to know) which flow
        created it.
        """
        transaction = await self.repo.get_by_id_for_update(tenant_id=None, id=transaction_id)
        if transaction is None:
            raise NotFoundError("Collection transaction not found")
        target = self._provider_for(transaction)
        await target.query_and_apply(transaction=transaction, actor_id=None)
        return transaction

    async def list_reconcilable(self) -> list[Transaction]:
        """Every non-terminal payment THIS PROVIDER owns that a periodic
        sweep should query — pure DB read, no Selcom awareness, safe for
        the worker (see app/tasks/collections.py).

        Scoped by `payment_provider`, deliberately NOT by
        transaction_type. Those answer different questions, and
        reconciliation needs the provider one: a captive-portal package
        payment settled through Selcom must be swept exactly like a tenant
        Collection, while a future voucher/cash captive payment must never
        be sent to Selcom's order-status at all. This is the exact
        opposite of the tenant dashboard's type-scoped list, which stays
        on transaction_type=COLLECTION and must never widen.

        Rows with a NULL provider are excluded rather than assumed. That
        is safe because every writer that can produce a non-terminal
        Selcom row sets payment_provider explicitly, and the c4f81b2e9a37
        backfill classified every historical COLLECTION row — an
        ordering the Phase 3 rollout depended on. A NULL-provider row is
        visible for review, never silently queried against a provider it
        may never have reached.
        """
        non_terminal = [
            status.value
            for status in CollectionStatus
            if status not in COLLECTION_TERMINAL_STATUSES
        ]
        return await self.repo.list_reconcilable_by_provider(
            payment_provider=self._flow.payment_provider.value, statuses=non_terminal
        )

    # ----------------------------------------------------------- webhook

    async def process_webhook(self, *, headers: dict[str, str], body: bytes) -> dict[str, str]:
        """Selcom's own docs: webhook only fires on successful
        transactions, and never signs amount/channel/phone — so this is
        used ONLY as a signal to go query order-status (an authenticated
        request we sign ourselves) before ever touching a wallet. See
        app/api/v1/webhooks.py for the route.

        One Selcom callback URL serves every flow. The row this finds by
        order_id is dispatched via _provider_for to the flow that
        actually created it before query_and_apply ever runs — fixed
        2026-09-20 after a captive-portal payment was finalized as a
        plain tenant Collection (wallet credited correctly, but never
        activated, and un-fixable after the fact once terminal) because
        this used to always finalize with THIS provider's own flow.
        """
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
                self._logger.warning(
                    f"{self._flow.log_namespace}.webhook_verification_failed", detail=str(exc)
                )

        webhook_row = await webhook_repo.create(
            tenant_id=None,
            provider="selcom_collection",
            payload=raw_payload,
            signature_verified=signature_verified,
            processed=False,
        )

        if not signature_verified:
            await webhook_repo.update(webhook_row, processed=True, processed_at=datetime.now(UTC))
            return {"status": "rejected"}

        payload = WebhookPayload.model_validate(raw_payload)
        if not payload.order_id:
            await webhook_repo.update(webhook_row, processed=True, processed_at=datetime.now(UTC))
            return {"status": "malformed"}

        transaction = await self.repo.get_by_reference_for_update(reference=payload.order_id)
        if transaction is None:
            await webhook_repo.update(webhook_row, processed=True, processed_at=datetime.now(UTC))
            self._logger.warning(
                f"{self._flow.log_namespace}.webhook_unknown_order", order_id=payload.order_id
            )
            return {"status": "unknown_reference"}

        await webhook_repo.update(webhook_row, tenant_id=transaction.tenant_id)
        target = self._provider_for(transaction)
        await write_audit_log(
            self.db,
            tenant_id=transaction.tenant_id,
            actor_id=None,
            action=f"{target._flow.audit_namespace}.webhook_received",
            target_type="transaction",
            target_id=transaction.id,
        )
        await target.query_and_apply(transaction=transaction, actor_id=None)
        await webhook_repo.update(webhook_row, processed=True, processed_at=datetime.now(UTC))
        return {"status": "acknowledged"}
