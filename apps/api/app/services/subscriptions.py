from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PackageActivationType, PackageStatus, SubscriptionStatus
from app.core.errors import DomainValidationError, NotFoundError
from app.core.pagination import ListParams
from app.models.network import Package, Subscription
from app.repositories.billing import PackageRepository, SubscriptionRepository
from app.repositories.customers import CustomerRepository
from app.services.audit import write_audit_log


class SubscriptionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = SubscriptionRepository(db)
        self.customer_repo = CustomerRepository(db)
        self.package_repo = PackageRepository(db)

    async def list(self, *, tenant_id: UUID, params: ListParams) -> tuple[list[Subscription], int]:
        return await self.repo.list_paginated(tenant_id=tenant_id, params=params)

    async def get(self, *, tenant_id: UUID, subscription_id: UUID) -> Subscription:
        subscription = await self.repo.get_by_id(tenant_id=tenant_id, id=subscription_id)
        if subscription is None:
            raise NotFoundError("Subscription not found")
        return subscription

    async def create(
        self, *, tenant_id: UUID, actor_id: UUID, customer_id: UUID, package_id: UUID
    ) -> Subscription:
        """Staff-assigned subscription — no voucher involved."""
        customer = await self.customer_repo.get_by_id(tenant_id=tenant_id, id=customer_id)
        if customer is None:
            raise DomainValidationError("customer_id does not belong to this tenant")

        package = await self.package_repo.get_by_id(tenant_id=tenant_id, id=package_id)
        if package is None:
            raise DomainValidationError("package_id does not belong to this tenant")
        if package.status != PackageStatus.ACTIVE:
            raise DomainValidationError("This package is no longer active")

        return await self._create(
            tenant_id=tenant_id,
            actor_id=actor_id,
            customer_id=customer_id,
            package=package,
            voucher_id=None,
        )

    async def create_from_voucher(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        customer_id: UUID,
        package: Package,
        voucher_id: UUID,
    ) -> Subscription:
        """Called by VoucherService.redeem() as part of one redemption
        transaction — the caller has already locked the voucher and
        validated the package belongs to this tenant and is active."""
        return await self._create(
            tenant_id=tenant_id,
            actor_id=actor_id,
            customer_id=customer_id,
            package=package,
            voucher_id=voucher_id,
        )

    async def create_awaiting_payment(
        self, *, tenant_id: UUID, customer_id: UUID, package_id: UUID
    ) -> Subscription:
        """Called by the captive portal's payment-initiation flow (see
        app/services/captive_portal.py). Unlike create()/create_from_voucher,
        this NEVER auto-activates regardless of the package's
        activation_type — payment hasn't cleared yet, so the subscription
        must stay PENDING until CaptivePortalService confirms the
        transaction and calls activate() itself."""
        customer = await self.customer_repo.get_by_id(tenant_id=tenant_id, id=customer_id)
        if customer is None:
            raise DomainValidationError("customer_id does not belong to this tenant")

        package = await self.package_repo.get_by_id(tenant_id=tenant_id, id=package_id)
        if package is None:
            raise DomainValidationError("package_id does not belong to this tenant")
        if package.status != PackageStatus.ACTIVE:
            raise DomainValidationError("This package is no longer active")

        subscription = await self.repo.create(
            tenant_id=tenant_id,
            customer_id=customer_id,
            package_id=package.id,
            voucher_id=None,
            status=SubscriptionStatus.PENDING,
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=None,
            action="subscription.created_awaiting_payment",
            target_type="subscription",
            target_id=subscription.id,
        )
        return subscription

    async def _create(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        customer_id: UUID,
        package: Package,
        voucher_id: UUID | None,
    ) -> Subscription:
        subscription = await self.repo.create(
            tenant_id=tenant_id,
            customer_id=customer_id,
            package_id=package.id,
            voucher_id=voucher_id,
            status=SubscriptionStatus.PENDING,
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="subscription.created",
            target_type="subscription",
            target_id=subscription.id,
        )

        if package.activation_type == PackageActivationType.IMMEDIATE:
            subscription = await self.activate(
                tenant_id=tenant_id, actor_id=actor_id, subscription_id=subscription.id
            )

        return subscription

    async def activate(
        self, *, tenant_id: UUID, actor_id: UUID | None, subscription_id: UUID
    ) -> Subscription:
        """The single place a subscription transitions PENDING -> ACTIVE.
        Locks the subscription row first so two concurrent activation
        attempts (e.g. a retried voucher redemption) can't both succeed —
        the caller commits the surrounding transaction once done."""
        subscription = await self.repo.get_by_id_for_update(
            tenant_id=tenant_id, id=subscription_id
        )
        if subscription is None:
            raise NotFoundError("Subscription not found")
        if subscription.status != SubscriptionStatus.PENDING:
            raise DomainValidationError(
                f"Subscription cannot be activated from status {subscription.status}"
            )

        package = await self.package_repo.get_by_id(
            tenant_id=tenant_id, id=subscription.package_id
        )
        if package is None:
            raise DomainValidationError("Subscription's package no longer exists")

        activated_at = datetime.now(UTC)
        expires_at = (
            activated_at + timedelta(minutes=package.duration_minutes)
            if package.duration_minutes
            else None
        )

        subscription = await self.repo.update(
            subscription,
            status=SubscriptionStatus.ACTIVE,
            activated_at=activated_at,
            expires_at=expires_at,
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="subscription.activated",
            target_type="subscription",
            target_id=subscription.id,
        )
        return subscription
