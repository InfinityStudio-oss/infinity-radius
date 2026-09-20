"""Orchestrates the public captive portal flow described in the Add Router
Wizard's redirect contract: a signed router token resolves to a tenant,
branding and ACTIVE packages load for that tenant, a customer picks a
package and gives a phone number, a Transaction + PENDING Subscription are
created, and a safe public transaction token lets the waiting screen poll
status — never a database id.

Payment confirmation (`mark_transaction_completed`) is what
`POST /api/v1/webhooks/selcom/collection`
(app/integrations/selcom/collection.py's CollectionService.process_callback)
calls once a callback is genuinely verified. That verification step
itself is still a documented TODO pending Selcom's official API docs (see
app/integrations/selcom/signatures.py) — so this method is real, reachable,
and directly tested (activation, RADIUS provisioning, the wallet's
gross -> platform fee / tenant share split via WalletService.process_collection,
and the audit trail all genuinely happen), but nothing external can
trigger it for real money yet, because nothing can yet prove a callback is
authentically from Selcom.
"""

import secrets
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import PackageStatus, TransactionType
from app.core.errors import DomainValidationError, NotFoundError
from app.core.money import DEFAULT_CURRENCY
from app.core.transaction_token import create_transaction_token, resolve_transaction_token
from app.integrations.selcom.client import SelcomClient
from app.integrations.selcom.config import SelcomConfig
from app.integrations.selcom.exceptions import SelcomNotConfiguredError, SelcomNotImplementedError
from app.integrations.selcom.schemas import CollectionOrderRequest
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
from app.services.subscriptions import SubscriptionService
from app.services.wallet import WalletService


def selcom_config_from_settings() -> SelcomConfig:
    settings = get_settings()
    return SelcomConfig(
        api_base_url=settings.selcom_api_base_url,
        api_key=settings.selcom_api_key,
        api_secret=settings.selcom_api_secret,
        merchant_id=settings.selcom_merchant_id,
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

        provider_configured = True
        selcom = SelcomClient(selcom_config_from_settings())
        try:
            order_response = await selcom.collection.initiate_collection(
                CollectionOrderRequest(
                    reference=reference,
                    amount=amount,
                    currency=DEFAULT_CURRENCY,
                    customer_phone=customer.phone,
                    # Only ever a real customer-supplied email, never a
                    # placeholder — customer.email is None for the common
                    # phone-only captive-portal signup.
                    customer_email=customer.email,
                )
            )
        except (SelcomNotConfiguredError, SelcomNotImplementedError):
            provider_configured = False
        else:
            if order_response.provider_reference:
                transaction = await self.transaction_repo.update(
                    transaction, provider_reference=order_response.provider_reference
                )

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
        """Called by CollectionService.process_callback once (and only
        once) a Selcom Collection callback has been genuinely verified,
        its reference/amount/state validated against this transaction, and
        idempotency confirmed (not already processed). Activates the
        subscription, credits the tenant's wallet, provisions RADIUS
        access, and writes the audit trail — all real, all tested.
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
