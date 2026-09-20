"""Orchestrates the public captive portal flow described in the Add Router
Wizard's redirect contract: a signed router token resolves to a tenant,
branding and ACTIVE packages load for that tenant, a customer picks a
package and gives a phone number, a Transaction + PENDING Subscription are
created, and a safe public transaction token lets the waiting screen poll
status — never a database id.

NO PAYMENT PROVIDER IS WIRED UP HERE YET. `initiate_payment` creates the
Transaction and PENDING Subscription and then reports
`provider_not_configured` — it contacts nobody. It previously called a
legacy Selcom Collection stub that could only ever raise, which has been
removed; the observable result is unchanged, and deliberately so.

The validated Mobile Checkout provider that will replace it lives in
app/services/selcom_payment_provider.py, already shared with the tenant
Collection flow. Wiring it up is a later phase — see docs/architecture.md.

Payment confirmation (`mark_transaction_completed`) is therefore real,
directly tested (activation, RADIUS provisioning, the wallet's
gross -> platform fee / tenant share split via WalletService.process_collection,
and the audit trail all genuinely happen) but currently reachable only
from tests, since nothing yet initiates a real captive-portal payment.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import (
    COLLECTION_TERMINAL_STATUSES,
    ActivationStatus,
    CollectionStatus,
    PackageStatus,
    PaymentProvider,
    TransactionType,
)
from app.core.errors import DomainValidationError, NotFoundError
from app.core.money import DEFAULT_CURRENCY
from app.core.phone import normalize_tz_phone
from app.core.transaction_token import create_transaction_token, resolve_transaction_token
from app.integrations.selcom_collection.schemas import OrderStatusData
from app.models.finance import Transaction
from app.models.network import Customer, Package
from app.repositories.billing import PackageRepository
from app.repositories.finance import TransactionRepository
from app.repositories.network import RouterRepository
from app.repositories.tenancy import TenantRepository
from app.schemas.captive_portal import (
    CaptivePortalBrandingRead,
    CaptivePortalPaymentInitiateResult,
    CaptivePortalPaymentStatusResult,
)
from app.services.audit import write_audit_log
from app.services.captive_rate_limit import CaptiveRateLimiter
from app.services.captive_session import (
    CaptivePortalSessionService,
    CaptiveSessionError,
    validate_package_ownership,
)
from app.services.customers import CustomerService
from app.services.radius_sync import (
    derive_radius_password,
)
from app.services.selcom_payment_provider import SelcomPaymentFlow, SelcomPaymentProvider
from app.services.subscriptions import SubscriptionService
from app.services.wallet import WalletService

# The identity the captive-portal flow WILL use once it is wired to the
# validated provider. Declared here now so the writer and the reconciliation
# sweep are defined together and cannot drift: the moment initiate_payment
# calls SelcomPaymentProvider, it passes this, and every row it creates is
# discovered by the provider-scoped sweep automatically.
#
# transaction_type stays CAPTIVE_PORTAL — the business flow — while
# payment_provider is SELCOM_COLLECTION. That pairing is the whole point of
# having two columns: these rows must be reconciled exactly like a tenant
# Collection, yet must NEVER appear in the tenant Collections dashboard.
#
# NOT WIRED UP. initiate_payment below deliberately does NOT set
# payment_provider today, because it contacts no provider at all — see its
# body. Writing SELCOM_COLLECTION on a row that never reached Selcom would
# fabricate history AND make the sweep query order-status for an order_id
# that was never created.
# Which stored CollectionStatus values the customer-facing portal shows as
# "failed". Derived from COLLECTION_TERMINAL_STATUSES minus COMPLETED, so a
# status added there can never silently project to "pending" forever and
# leave a customer watching a spinner for a payment that already died.
# REQUIRES_REVIEW and AMBIGUOUS are deliberately NOT here: they are still
# being reconciled, and telling someone their payment failed while it may
# yet settle is how you get charged-but-told-it-failed complaints.
# One customer-facing sentence for every reason online payment is closed —
# an expired gate, a disabled integration, a missing credential. Operators
# get the real reason from logs and audit; the customer gets something
# actionable and identical in every case, so the endpoint cannot be probed
# to learn which control is in force.
UNAVAILABLE_MESSAGE = (
    "Online payment is not available on this network yet. "
    "Please contact your network administrator."
)


def mask_msisdn(phone: str) -> str:
    """2557*****101 — the only form of a payer number that may appear in an
    audit row, a log line or an API response."""
    if len(phone) < 7:
        return "*" * len(phone)
    return f"{phone[:4]}{'*' * (len(phone) - 7)}{phone[-3:]}"


_PUBLIC_FAILED_STATUSES = frozenset(
    status.value
    for status in COLLECTION_TERMINAL_STATUSES
    if status is not CollectionStatus.COMPLETED
)

# Still genuinely being verified by the provider. Projected as "pending"
# with under_review=True so the portal can tell the customer NOT to pay
# again — REQUIRES_REVIEW/AMBIGUOUS may still settle, and a second payment
# on top of one that later succeeds is a real double charge.
_UNDER_REVIEW_STATUSES = frozenset(
    {CollectionStatus.REQUIRES_REVIEW.value, CollectionStatus.AMBIGUOUS.value}
)

# Internal ActivationStatus -> the coarse word the customer sees.
_PUBLIC_ACTIVATION = {
    ActivationStatus.PENDING.value: "pending",
    ActivationStatus.ACTIVATING.value: "activating",
    ActivationStatus.ACTIVE.value: "active",
    ActivationStatus.FAILED.value: "failed",
    # An operator flag, not a customer-facing distinction — a customer in
    # this state is simply still waiting for access, not told to act.
    ActivationStatus.REQUIRES_REVIEW.value: "failed",
}

# An attempt still in flight. A duplicate POST matching one of these
# reuses it; once an attempt reaches ANY terminal status it stops
# matching, so a customer can deliberately try again after a genuine
# failure — they just cannot start a second one by accident while the
# first is still live.
_NON_TERMINAL_STATUSES = [
    status.value
    for status in CollectionStatus
    if status not in COLLECTION_TERMINAL_STATUSES
]


CAPTIVE_PORTAL_SELCOM_FLOW = SelcomPaymentFlow(
    transaction_type=TransactionType.CAPTIVE_PORTAL,
    payment_provider=PaymentProvider.SELCOM_COLLECTION,
    reference_prefix="CP-",
    audit_namespace="captive_portal",
    log_namespace="captive_portal",
)


class CaptivePortalService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.router_repo = RouterRepository(db)
        self.tenant_repo = TenantRepository(db)
        self.package_repo = PackageRepository(db)
        self.transaction_repo = TransactionRepository(db)
        # Exposed the same way CollectionService exposes its own, so the
        # shared provider layer's cross-flow dispatch
        # (SelcomPaymentProvider._provider_for — see the 2026-09-20
        # incident) can reach this flow's finalizer from outside this
        # class without re-implementing it.
        self.provider = SelcomPaymentProvider(
            db, flow=CAPTIVE_PORTAL_SELCOM_FLOW, finalize_payment=self._finalize_captive_payment
        )

    async def resolve_tenant_id_for_router(self, router_id: UUID) -> UUID | None:
        """The one place a router token turns into a tenant — everything
        else in this service takes tenant_id as already resolved, so it's
        never re-derived from client input more than once per request."""
        router_row = await self.router_repo.get_by_id(tenant_id=None, id=router_id)
        return router_row.tenant_id if router_row is not None else None

    async def get_branding(self, *, tenant_id: UUID) -> CaptivePortalBrandingRead:
        tenant = await self.tenant_repo.get_by_id(tenant_id=None, id=tenant_id)
        if tenant is None:
            raise NotFoundError("Tenant not found")
        return CaptivePortalBrandingRead(
            tenant_name=tenant.name, logo_url=tenant.logo_url, brand_color=tenant.brand_color
        )

    async def initiate_payment(
        self,
        *,
        intent_token: str,
        package_id: UUID,
        phone: str,
    ) -> CaptivePortalPaymentInitiateResult:
        """Starts ONE captive-portal payment against the validated Selcom
        provider.

        ORDER MATTERS and is load-bearing. The production kill switch is
        checked FIRST — before the session is consumed, before a customer,
        subscription or transaction row exists, and long before any
        provider contact. A closed gate must leave behind no orphan
        subscription and no payment attempt to reconcile.

        The browser supplies an intent token, a package and a phone
        number. Everything financial — tenant, router, price, currency,
        commercial terms — is resolved server-side from the session's own
        router row. `amount` is not a field on the request model at all,
        so a tampered request cannot under-pay for a package.
        """
        settings = get_settings()

        # --- GATE FIRST: no persistence, no provider contact ------------
        if (
            not settings.selcom_collection_enabled
            or not settings.selcom_collection_production_enabled
        ):
            # Two independent kill switches, the same pair the tenant
            # Collection flow respects — captive payments must never be a
            # way around them. Returning here means no session consumed,
            # no customer, no subscription, no transaction, no provider
            # call: nothing to reconcile or clean up later.
            return CaptivePortalPaymentInitiateResult(
                status="unavailable",
                message=UNAVAILABLE_MESSAGE,
            )

        session_service = CaptivePortalSessionService(self.db)
        try:
            session = await session_service.resolve(intent_token=intent_token)
        except CaptiveSessionError as exc:
            raise DomainValidationError(
                "This payment session has expired. Please start again."
            ) from exc

        # Looked up scoped to the SESSION's tenant, so a package id
        # belonging to another tenant simply does not resolve.
        package = await self.package_repo.get_by_id(
            tenant_id=session.tenant_id, id=package_id
        )
        if package is None:
            raise DomainValidationError("package_id does not belong to this router's tenant")
        validate_package_ownership(
            package_tenant_id=package.tenant_id, session_tenant_id=session.tenant_id
        )
        if package.status != PackageStatus.ACTIVE:
            raise DomainValidationError("This package is no longer available")

        # THE authoritative amount. Server-derived from the package row,
        # never from the request.
        amount = Decimal(package.price_tzs)

        try:
            normalized_phone = normalize_tz_phone(phone)
        except ValueError as exc:
            raise DomainValidationError(str(exc)) from exc

        # --- abuse controls, before anything is created -----------------
        decision = await CaptiveRateLimiter().check(
            session_id=session.id, phone=normalized_phone, router_id=session.router_id
        )
        if not decision.allowed:
            await write_audit_log(
                self.db,
                tenant_id=session.tenant_id,
                actor_id=None,
                action="captive_portal.rate_limited",
                target_type="captive_session",
                target_id=session.id,
                metadata={"dimension": decision.dimension},
            )
            return CaptivePortalPaymentInitiateResult(
                status="rate_limited",
                message="Too many payment attempts. Please wait a few minutes and try again.",
            )

        # --- duplicate suppression: reuse, never re-send ----------------
        existing = await self.transaction_repo.find_active_captive_attempt(
            captive_session_id=session.id,
            package_id=package.id,
            payer_phone=normalized_phone,
            non_terminal_statuses=_NON_TERMINAL_STATUSES,
        )
        if existing is not None:
            # A double-click, refresh, second tab or HTTP retry lands here.
            # The customer gets their ORIGINAL attempt back — no second
            # transaction, and crucially no second STK to their handset.
            await write_audit_log(
                self.db,
                tenant_id=session.tenant_id,
                actor_id=None,
                action="captive_portal.duplicate_attempt_suppressed",
                target_type="transaction",
                target_id=existing.id,
                metadata={"captive_session_id": str(session.id)},
            )
            return CaptivePortalPaymentInitiateResult(
                transaction_token=create_transaction_token(existing.id),
                status="duplicate",
                amount=amount,
                currency=DEFAULT_CURRENCY,
                message=(
                    "We are already processing a payment request for this package. "
                    "Check your phone for the payment prompt."
                ),
            )

        customer = await CustomerService(self.db).get_or_create_by_phone(
            tenant_id=session.tenant_id, phone=normalized_phone
        )
        subscription = await SubscriptionService(self.db).create_awaiting_payment(
            tenant_id=session.tenant_id, customer_id=customer.id, package_id=package.id
        )

        reference = self.provider.new_reference()

        transaction = await self.transaction_repo.create(
            tenant_id=session.tenant_id,
            customer_id=customer.id,
            subscription_id=subscription.id,
            # Business flow and settling provider, set together from the
            # flow constant so they cannot drift. This row IS a captive
            # purchase AND IS settled by Selcom — that pairing is exactly
            # why the two columns exist.
            transaction_type=CAPTIVE_PORTAL_SELCOM_FLOW.transaction_type.value,
            payment_provider=CAPTIVE_PORTAL_SELCOM_FLOW.payment_provider.value,
            package_id=package.id,
            router_id=session.router_id,
            captive_session_id=session.id,
            device_mac=session.mac_address,
            payer_phone=normalized_phone,
            reference=reference,
            channel="captive_portal",
            amount=str(amount),
            currency=DEFAULT_CURRENCY,
            status=CollectionStatus.CREATED.value,
        )

        # Single-use: spent now that an attempt genuinely exists, so a
        # replayed token cannot open a second one.
        await session_service.consume(session=session)

        await write_audit_log(
            self.db,
            tenant_id=session.tenant_id,
            actor_id=None,
            action="captive_portal.payment_initiated",
            target_type="transaction",
            target_id=transaction.id,
            metadata={
                "reference": reference,
                "package_id": str(package.id),
                "router_id": str(session.router_id),
                # Masked, never the raw msisdn.
                "payer_phone_masked": mask_msisdn(normalized_phone),
                "amount": str(amount),
            },
        )

        buyer_name = (
            " ".join(part for part in (customer.first_name, customer.last_name) if part).strip()
            or normalized_phone
        )
        buyer_email = customer.email or f"{normalized_phone}@customer.invalid"

        # The SAME validated provider layer the tenant Collection flow
        # uses. Signing, create-order-minimal, wallet-payment and the
        # order-status state machine are NOT duplicated here.
        #
        # description is deliberately left unset (None), matching the
        # validated manual Collection request exactly — see the
        # 2026-09-20 captive HTTP 403 investigation. merchant_remarks is
        # the one field this call used to add that the manual flow's
        # known-good request never sends, which also changes the
        # dynamically-built Signed-Fields set (see
        # app/integrations/selcom_collection/client.py's
        # create_order_minimal — merchant_remarks is only included in the
        # signed request when non-None). The package name has no
        # functional use on Selcom's side; it is not worth carrying a
        # request-shape delta from the validated path to send it.
        transaction = await self.provider.create_order_and_send_stk(
            transaction,
            actor_id=None,
            buyer_name=buyer_name,
            buyer_email=buyer_email,
            msisdn=normalized_phone,
            amount=amount,
            currency=DEFAULT_CURRENCY,
            description=None,
        )

        # Report what genuinely happened, not an assumed success. The two
        # only possible outcomes of create_order_and_send_stk are
        # STK_SENT (both provider calls succeeded) or FAILED (either one
        # didn't) — see that method. Telling a customer to check a phone
        # that will never buzz is worse than an honest failure message.
        if transaction.status == CollectionStatus.STK_SENT.value:
            return CaptivePortalPaymentInitiateResult(
                transaction_token=create_transaction_token(transaction.id),
                status="pending",
                amount=amount,
                currency=DEFAULT_CURRENCY,
                message="Check your phone and approve the payment prompt.",
            )

        return CaptivePortalPaymentInitiateResult(
            transaction_token=create_transaction_token(transaction.id),
            status="failed",
            amount=amount,
            currency=DEFAULT_CURRENCY,
            message="We could not start this payment. Please try again in a moment.",
        )

    async def _finalize_captive_payment(
        self, transaction: Transaction, status_data: OrderStatusData
    ) -> None:
        """What a verified COMPLETED payment means for this flow: credit
        the tenant's wallet, through the tenant's own commercial terms,
        exactly as a manual Collection does.

        Invoked by SelcomPaymentProvider only after an authenticated
        order-status query matched order_id, amount and currency exactly.
        Deliberately does NOT activate access — see
        app/services/captive_activation.py for why that must run in its
        own transaction.
        """
        await WalletService(self.db).process_collection(
            tenant_id=transaction.tenant_id,
            gross_amount=Decimal(transaction.amount),
            # Same reference_type as the tenant Collection flow so ledger
            # queries stay uniform. The CAPTIVE_PORTAL identity lives in
            # transaction_type, the description and the audit trail.
            reference_type="selcom_collection",
            reference_id=transaction.id,
            description=f"Captive portal payment {transaction.reference}",
        )
        # Paid, access not yet granted — immediately visible to the retry
        # sweep even if this process dies before activation is attempted.
        await self.transaction_repo.update(
            transaction, activation_status=ActivationStatus.PENDING.value
        )

    async def reconcile(self, *, transaction_id: UUID) -> Transaction:
        """The captive-portal counterpart of CollectionService.reconcile.

        In practice this is only ever reached via
        SelcomPaymentProvider._provider_for's cross-flow dispatch — the
        shared webhook and the payment_provider-scoped reconciliation
        sweep both discover transactions by payment_provider, not by
        transaction_type, so either can hand a CAPTIVE_PORTAL id to
        CollectionService's own reconcile path. Exposed directly here too
        so a captive-specific caller never has to go through
        CollectionService to reach it.
        """
        return await self.provider.reconcile(transaction_id=transaction_id)

    async def get_payment_status(self, *, token: str) -> CaptivePortalPaymentStatusResult:
        """Everything the waiting screen is allowed to know about ONE
        attempt.

        Scoped by an opaque transaction token, never a database id, so a
        client cannot enumerate or read anyone else's payment. What comes
        back is a deliberate projection: coarse payment state, activation
        state, the package and price the customer already agreed to, and a
        masked phone. Never a wallet balance, a ledger entry, a commission
        rate, a raw msisdn, or anything about another transaction.
        """
        transaction_id = resolve_transaction_token(token)
        if transaction_id is None:
            return CaptivePortalPaymentStatusResult(status="not_found")

        # tenant_id=None: the token is the only thing establishing which
        # transaction (and tenant) this is about.
        transaction = await self.transaction_repo.get_by_id(tenant_id=None, id=transaction_id)
        if transaction is None:
            return CaptivePortalPaymentStatusResult(status="not_found")

        package_name = None
        if transaction.package_id is not None:
            package = (
                await self.db.execute(
                    select(Package).where(Package.id == transaction.package_id)
                )
            ).scalar_one_or_none()
            package_name = package.name if package is not None else None

        common: dict[str, object] = {
            "package_name": package_name,
            "amount": transaction.amount,
            "currency": transaction.currency,
            "payer_phone_masked": (
                mask_msisdn(transaction.payer_phone) if transaction.payer_phone else None
            ),
            "created_at": transaction.created_at,
        }

        # --- still being verified: the one state where telling the truth
        # --- badly causes a double charge --------------------------------
        if transaction.status in _UNDER_REVIEW_STATUSES:
            return CaptivePortalPaymentStatusResult(
                status="pending",
                under_review=True,
                message=(
                    "We are still confirming your payment with your mobile money "
                    "provider. Please do NOT pay again — if money left your account "
                    "it will be applied to this purchase."
                ),
                **common,
            )

        if transaction.status in _PUBLIC_FAILED_STATUSES:
            return CaptivePortalPaymentStatusResult(
                status="failed",
                message=(
                    "The payment was not completed. You have not been charged for "
                    "a plan you did not get. You can try again."
                ),
                **common,
            )

        if transaction.status != CollectionStatus.COMPLETED.value:
            # CREATED / STK_SENT / PENDING / INPROGRESS, plus anything
            # unrecognised — which projects here rather than to success.
            return CaptivePortalPaymentStatusResult(
                status="pending",
                message="Check your phone and approve the payment prompt.",
                **common,
            )

        # --- paid. Now: is access actually live? ------------------------
        activation = _PUBLIC_ACTIVATION.get(transaction.activation_status or "", "pending")
        result_common = {
            **common,
            "completed_at": transaction.completed_at,
            "activated_at": transaction.activated_at,
            "provider_reference": transaction.provider_reference,
            "activation_status": activation,
        }

        if activation != "active":
            # Paid but not yet online. Credentials are deliberately
            # withheld: handing over a RADIUS password before provisioning
            # succeeded would just produce a login FreeRADIUS rejects.
            return CaptivePortalPaymentStatusResult(
                status="completed",
                message=(
                    "Payment confirmed. We are setting up your internet access — "
                    "this only takes a moment."
                    if activation != "failed"
                    else "Payment confirmed. We could not finish setting up your "
                    "access automatically — our team has been notified and you "
                    "have NOT been charged twice."
                ),
                **result_common,
            )

        if transaction.subscription_id is None or transaction.customer_id is None:
            return CaptivePortalPaymentStatusResult(
                status="completed", **result_common
            )

        customer = (
            await self.db.execute(
                select(Customer).where(Customer.id == transaction.customer_id)
            )
        ).scalar_one_or_none()
        if customer is None:
            return CaptivePortalPaymentStatusResult(
                status="completed", **result_common
            )

        return CaptivePortalPaymentStatusResult(
            status="completed",
            message="You are connected. Enjoy your internet.",
            login_username=customer.phone,
            login_password=derive_radius_password(transaction.subscription_id),
            **result_common,
        )

    async def finalize_payment(self, *, transaction_id: UUID) -> None:
        """Finalizes the MONEY for one captive-portal payment, and nothing
        else. Row-locked and idempotent.

        Deliberately does NOT activate the subscription or provision
        RADIUS — see app/services/captive_activation.py. Those run in a
        SEPARATE transaction opened after this one commits, so that a
        FreeRADIUS outage can never roll back a payment the customer has
        genuinely made. Splitting them is the whole point: a verified
        COMPLETED payment must never become a failure because access
        provisioning failed.

        Marks activation_status=PENDING so the payment is immediately
        visible to the retry sweep even if the process dies before
        activation is attempted.

        Accounting is identical to the tenant Collection flow: the same
        WalletService.process_collection, the same commercial terms, the
        same three ledger entries.
        """
        transaction = await self.transaction_repo.get_by_id_for_update(
            tenant_id=None, id=transaction_id
        )
        if transaction is None:
            raise NotFoundError("Transaction not found")

        if transaction.status == CollectionStatus.COMPLETED.value:
            return  # already finalized — never credit the wallet twice

        # Only a non-terminal payment may be finalized. A CANCELLED or
        # FAILED row must never be resurrected into a credit.
        if transaction.status in _PUBLIC_FAILED_STATUSES:
            raise DomainValidationError(
                f"Cannot finalize a payment already terminal in status {transaction.status}"
            )

        if transaction.subscription_id is None or transaction.customer_id is None:
            raise DomainValidationError("Transaction has no associated subscription/customer")

        await self.transaction_repo.update(
            transaction,
            status=CollectionStatus.COMPLETED.value,
            completed_at=datetime.now(UTC),
            # Paid, access not yet granted. The retry sweep picks this up.
            activation_status=ActivationStatus.PENDING.value,
        )

        await WalletService(self.db).process_collection(
            tenant_id=transaction.tenant_id,
            gross_amount=Decimal(transaction.amount),
            reference_type="transaction",
            reference_id=transaction.id,
            description=f"Captive portal payment {transaction.reference}",
        )

        await write_audit_log(
            self.db,
            tenant_id=transaction.tenant_id,
            actor_id=None,
            action="captive_portal.payment_completed",
            target_type="transaction",
            target_id=transaction.id,
            metadata={"subscription_id": str(transaction.subscription_id)},
        )
