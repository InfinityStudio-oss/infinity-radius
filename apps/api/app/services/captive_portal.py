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

import secrets
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PackageStatus, PaymentProvider, TransactionType
from app.core.errors import DomainValidationError, NotFoundError
from app.core.money import DEFAULT_CURRENCY
from app.core.transaction_token import create_transaction_token, resolve_transaction_token
from app.models.network import Customer, Package, Subscription
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
from app.services.customers import CustomerService
from app.services.radius_sync import (
    derive_radius_password,
    provision_customer_radius_access,
    sync_package_radius_group,
)
from app.services.selcom_payment_provider import SelcomPaymentFlow
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
        tenant_id: UUID,
        package_id: UUID,
        phone: str,
        mac_address: str | None = None,
    ) -> CaptivePortalPaymentInitiateResult:
        """Frontend sends only phone_number/package_id/router_token/
        mac_address — never an authoritative amount. The amount charged is
        always `package.price_tzs`, looked up server-side from the
        already-tenant-resolved package row; a client cannot influence it."""
        package = await self.package_repo.get_by_id(tenant_id=tenant_id, id=package_id)
        if package is None:
            raise DomainValidationError("package_id does not belong to this router's tenant")
        if package.status != PackageStatus.ACTIVE:
            raise DomainValidationError("This package is no longer available")

        # The official TZS amount — server-derived from the package, never
        # accepted from the client.
        amount = Decimal(package.price_tzs)

        customer = await CustomerService(self.db).get_or_create_by_phone(
            tenant_id=tenant_id, phone=phone
        )

        subscription = await SubscriptionService(self.db).create_awaiting_payment(
            tenant_id=tenant_id, customer_id=customer.id, package_id=package.id
        )

        reference = f"CP-{secrets.token_hex(8).upper()}"
        transaction = await self.transaction_repo.create(
            tenant_id=tenant_id,
            customer_id=customer.id,
            subscription_id=subscription.id,
            transaction_type=TransactionType.CAPTIVE_PORTAL.value,
            reference=reference,
            channel="captive_portal",
            amount=str(amount),
            currency=DEFAULT_CURRENCY,
            status="pending",
        )

        # No provider is wired up for captive-portal payments yet, so no
        # STK is ever requested and no provider is ever contacted — see
        # this module's docstring. Stated as one honest constant rather
        # than inferred from a call that could only ever fail.
        #
        # This is also why the row above deliberately carries NO
        # payment_provider: it has not reached one. Reconciliation
        # discovers work by payment_provider, so leaving it NULL is what
        # keeps the sweep from querying Selcom's order-status for an
        # order that was never created. CAPTIVE_PORTAL_SELCOM_FLOW above
        # is what sets it, once initiation genuinely goes to Selcom.
        provider_configured = False

        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=None,
            action="captive_portal.payment_initiated",
            target_type="transaction",
            target_id=transaction.id,
            metadata={
                "reference": reference,
                "provider_configured": provider_configured,
                "mac_address": mac_address,
            },
        )

        return CaptivePortalPaymentInitiateResult(
            transaction_token=create_transaction_token(transaction.id),
            status="pending" if provider_configured else "provider_not_configured",
            amount=amount,
            currency=DEFAULT_CURRENCY,
        )

    async def get_payment_status(self, *, token: str) -> CaptivePortalPaymentStatusResult:
        transaction_id = resolve_transaction_token(token)
        if transaction_id is None:
            return CaptivePortalPaymentStatusResult(status="not_found")

        # tenant_id=None: the token is the only thing establishing which
        # transaction (and tenant) this is about — same principle as
        # resolving a router token.
        transaction = await self.transaction_repo.get_by_id(tenant_id=None, id=transaction_id)
        if transaction is None:
            return CaptivePortalPaymentStatusResult(status="not_found")

        if transaction.status != "completed":
            status = transaction.status if transaction.status == "failed" else "pending"
            return CaptivePortalPaymentStatusResult(status=status)

        if transaction.subscription_id is None or transaction.customer_id is None:
            return CaptivePortalPaymentStatusResult(status="completed")

        customer_result = await self.db.execute(
            select(Customer).where(Customer.id == transaction.customer_id)
        )
        customer = customer_result.scalar_one_or_none()
        if customer is None:
            return CaptivePortalPaymentStatusResult(status="completed")

        return CaptivePortalPaymentStatusResult(
            status="completed",
            login_username=customer.phone,
            login_password=derive_radius_password(transaction.subscription_id),
        )

    async def mark_transaction_completed(self, *, transaction_id: UUID) -> None:
        """Finalizes one captive-portal payment: activates the
        subscription, credits the tenant's wallet, provisions RADIUS
        access, and writes the audit trail — all real, all tested.

        Guarded by the `status != "pending"` check below so a repeated
        call can never double-activate or double-credit. No production
        caller reaches this yet; when captive-portal payments are wired
        to SelcomPaymentProvider, this becomes that flow's
        `finalize_payment`, invoked only after an authenticated
        order-status query has verified the payment COMPLETED.
        """
        transaction = await self.transaction_repo.get_by_id(tenant_id=None, id=transaction_id)
        if transaction is None:
            raise NotFoundError("Transaction not found")
        if transaction.status != "pending":
            return  # already processed — idempotent, never double-activate

        if transaction.subscription_id is None or transaction.customer_id is None:
            raise DomainValidationError("Transaction has no associated subscription/customer")

        subscription_result = await self.db.execute(
            select(Subscription).where(Subscription.id == transaction.subscription_id)
        )
        subscription = subscription_result.scalar_one_or_none()
        if subscription is None:
            raise NotFoundError("Subscription not found")

        customer_result = await self.db.execute(
            select(Customer).where(Customer.id == transaction.customer_id)
        )
        customer = customer_result.scalar_one()

        package_result = await self.db.execute(
            select(Package).where(Package.id == subscription.package_id)
        )
        package = package_result.scalar_one()

        await self.transaction_repo.update(transaction, status="completed")
        subscription = await SubscriptionService(self.db).activate(
            tenant_id=transaction.tenant_id, actor_id=None, subscription_id=subscription.id
        )

        await WalletService(self.db).process_collection(
            tenant_id=transaction.tenant_id,
            gross_amount=Decimal(transaction.amount),
            reference_type="transaction",
            reference_id=transaction.id,
            description=f"Captive portal payment {transaction.reference}",
        )

        await sync_package_radius_group(
            package_id=package.id,
            download_speed_kbps=package.download_speed_kbps,
            upload_speed_kbps=package.upload_speed_kbps,
            session_timeout_seconds=(
                package.duration_minutes * 60 if package.duration_minutes else None
            ),
            simultaneous_sessions=package.simultaneous_sessions,
        )
        await provision_customer_radius_access(
            customer_phone=customer.phone,
            package_id=package.id,
            radius_password=derive_radius_password(subscription.id),
        )

        await write_audit_log(
            self.db,
            tenant_id=transaction.tenant_id,
            actor_id=None,
            action="captive_portal.payment_completed",
            target_type="transaction",
            target_id=transaction.id,
            metadata={"subscription_id": str(subscription.id)},
        )
