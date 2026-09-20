"""Tenant-facing Selcom Mobile Checkout Collection — a staff member
requests a mobile-money payment from a customer, and the tenant's wallet
is credited once (and only once) the payment is verified.

This module owns only what is SPECIFIC to that flow: the two kill-switch
gates, request validation, the customer lookup, the CAPTIVE_PORTAL-vs-
COLLECTION discriminator, and what finalization means here (credit the
tenant's wallet through the tenant's own commercial terms).

Everything provider-shaped — signing, create-order-minimal, the
wallet-payment STK push, the authenticated order-status state machine,
webhook verification — lives in app/services/selcom_payment_provider.py
and is shared with any other Selcom-backed flow. In particular the
wallet is still only ever credited from a value THIS process obtained
via a signed order-status query, never from an inbound webhook's own
claims; see that module for the full list of financial controls.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import CollectionStatus, PaymentProvider, TransactionType
from app.core.errors import DomainValidationError, NotFoundError
from app.core.phone import normalize_tz_phone
from app.integrations.selcom_collection.schemas import OrderStatusData
from app.models.finance import Transaction
from app.repositories.customers import CustomerRepository
from app.repositories.finance import TransactionRepository
from app.services.audit import write_audit_log
from app.services.selcom_payment_provider import SelcomPaymentFlow, SelcomPaymentProvider
from app.services.wallet import WalletService

# The tenant Collection flow's identity. `audit_namespace`/`log_namespace`
# reproduce the exact action and event strings this flow emitted before the
# provider was extracted, so existing audit history and log-based alerting
# stay continuous.
COLLECTION_FLOW = SelcomPaymentFlow(
    transaction_type=TransactionType.COLLECTION,
    payment_provider=PaymentProvider.SELCOM_COLLECTION,
    reference_prefix="col-",
    audit_namespace="collection",
    log_namespace="collections",
)


class CollectionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = TransactionRepository(db)
        self.customer_repo = CustomerRepository(db)
        self.wallet_service = WalletService(db)
        self.provider = SelcomPaymentProvider(
            db, flow=COLLECTION_FLOW, finalize_payment=self._credit_tenant_wallet
        )

    # ------------------------------------------------------ finalization

    async def _credit_tenant_wallet(
        self, transaction: Transaction, status_data: OrderStatusData
    ) -> None:
        """What a verified COMPLETED payment means for THIS flow: split
        the gross amount by the tenant's own active commercial terms and
        credit their pending balance. Runs inside the same row-locked
        transaction as the COMPLETED transition, and only ever from
        SelcomPaymentProvider.apply_order_status — which reaches it solely
        after an authenticated order-status query matched the order_id,
        amount and currency exactly."""
        await self.wallet_service.process_collection(
            tenant_id=transaction.tenant_id,
            gross_amount=Decimal(transaction.amount),
            reference_type="selcom_collection",
            reference_id=transaction.id,
            description=f"Selcom Collection {status_data.reference or transaction.reference}",
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
        """Creates the local Transaction row, then hands off to the
        provider for Create Order Minimal + the wallet-payment STK push —
        in that order, so a failure at any step leaves an honest,
        already-persisted FAILED record rather than nothing at all. Never
        sends a second STK for the same attempt: call this again only for
        a genuinely new attempt (a new Transaction row, a new order_id/
        transid) — see app/tasks/collections.py, which never calls this."""
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
            customer.email if customer else None
        ) or f"{normalized_phone}@customer.invalid"

        reference = self.provider.new_reference()

        transaction = await self.repo.create(
            tenant_id=tenant_id,
            customer_id=customer_id,
            transaction_type=COLLECTION_FLOW.transaction_type.value,
            # MUST be set here: reconciliation discovers work by
            # payment_provider (SelcomPaymentProvider.list_reconcilable), so
            # a row created without it would never be swept and a real
            # payment could sit unresolved forever. Both halves come from the
            # flow, so they can never drift apart.
            payment_provider=COLLECTION_FLOW.payment_provider.value,
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

        return await self.provider.create_order_and_send_stk(
            transaction,
            actor_id=actor_id,
            buyer_name=buyer_name,
            buyer_email=buyer_email,
            msisdn=normalized_phone,
            amount=amount,
            currency=currency,
            description=description,
        )

    # ------------------------------------------- reconciliation / webhook

    async def query_and_apply(self, *, transaction: Transaction, actor_id: UUID | None) -> None:
        """See SelcomPaymentProvider.query_and_apply. Assumes the caller
        already holds this transaction's row lock."""
        await self.provider.query_and_apply(transaction=transaction, actor_id=actor_id)

    async def reconcile(self, *, transaction_id: UUID) -> Transaction:
        """Public entry point for both the Super Admin-visible internal
        HMAC endpoint (worker-triggered) and any manual operator action —
        never called by a webhook directly (see process_webhook, which
        looks up by reference first)."""
        return await self.provider.reconcile(transaction_id=transaction_id)

    async def list_reconcilable_collections(self) -> list[Transaction]:
        """Every non-terminal Collection order a periodic sweep should
        query — pure DB read, no Selcom awareness, safe for the worker
        (see app/tasks/collections.py)."""
        return await self.provider.list_reconcilable()

    async def process_webhook(self, *, headers: dict[str, str], body: bytes) -> dict[str, str]:
        """Signal-only: see SelcomPaymentProvider.process_webhook. Selcom's
        callback never signs amount/channel/phone and only fires on
        success, so it is never trusted to credit a wallet on its own
        claims — it only triggers an authenticated order-status query."""
        return await self.provider.process_webhook(headers=headers, body=body)
