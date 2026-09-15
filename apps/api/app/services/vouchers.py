import secrets
import string
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PackageStatus, VoucherStatus
from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.core.pagination import ListParams
from app.models.network import OfflineVoucher, Subscription, VoucherBatch
from app.repositories.billing import (
    OfflineVoucherRepository,
    PackageRepository,
    VoucherBatchRepository,
)
from app.repositories.customers import CustomerRepository
from app.services.audit import write_audit_log
from app.services.subscriptions import SubscriptionService

# Cryptographically secure (secrets.choice, not random) and non-sequential —
# a voucher code must never be guessable from another code in the same batch.
_CODE_ALPHABET = string.ascii_uppercase + string.digits
_CODE_LENGTH = 10
_MAX_BATCH_QUANTITY = 5000


def _generate_code(prefix: str | None) -> str:
    body = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
    return f"{prefix}{body}" if prefix else body


class VoucherService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.batch_repo = VoucherBatchRepository(db)
        self.voucher_repo = OfflineVoucherRepository(db)
        self.package_repo = PackageRepository(db)
        self.customer_repo = CustomerRepository(db)

    async def list_batches(
        self, *, tenant_id: UUID, params: ListParams
    ) -> tuple[list[VoucherBatch], int]:
        return await self.batch_repo.list_paginated(tenant_id=tenant_id, params=params)

    async def list_vouchers(
        self, *, tenant_id: UUID, params: ListParams
    ) -> tuple[list[OfflineVoucher], int]:
        return await self.voucher_repo.list_paginated(tenant_id=tenant_id, params=params)

    async def get_batch(self, *, tenant_id: UUID, batch_id: UUID) -> VoucherBatch:
        batch = await self.batch_repo.get_by_id(tenant_id=tenant_id, id=batch_id)
        if batch is None:
            raise NotFoundError("Voucher batch not found")
        return batch

    async def generate_batch(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID,
        package_id: UUID,
        quantity: int,
        prefix: str | None,
    ) -> VoucherBatch:
        if quantity < 1 or quantity > _MAX_BATCH_QUANTITY:
            raise DomainValidationError(f"quantity must be between 1 and {_MAX_BATCH_QUANTITY}")

        package = await self.package_repo.get_by_id(tenant_id=tenant_id, id=package_id)
        if package is None:
            raise DomainValidationError("package_id does not belong to this tenant")

        batch = await self.batch_repo.create(
            tenant_id=tenant_id,
            package_id=package_id,
            quantity=quantity,
            prefix=prefix,
            created_by=actor_id,
        )

        # Codes must be unique per tenant — regenerate on the rare collision
        # rather than letting the unique constraint fail the whole batch.
        created = 0
        attempts = 0
        max_attempts = quantity * 5 + 20
        while created < quantity and attempts < max_attempts:
            attempts += 1
            code = _generate_code(prefix)
            if await self.voucher_repo.exists_by_code(tenant_id=tenant_id, code=code):
                continue
            await self.voucher_repo.create(
                tenant_id=tenant_id, batch_id=batch.id, code=code, status=VoucherStatus.UNUSED
            )
            created += 1

        if created < quantity:
            raise DomainValidationError(
                "Could not generate enough unique voucher codes — try a shorter prefix"
            )

        await self.db.flush()

        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="voucher_batch.generated",
            target_type="voucher_batch",
            target_id=batch.id,
            metadata={"quantity": quantity},
        )
        return batch

    async def redeem(
        self, *, tenant_id: UUID, actor_id: UUID, code: str, customer_id: UUID
    ) -> tuple[OfflineVoucher, Subscription]:
        """The one voucher-redemption transaction: lock the voucher row,
        validate tenant + UNUSED, load the package, create/activate the
        subscription, mark the voucher USED, write an audit event. Every
        step runs against the same request-scoped session/transaction — the
        caller commits once at the end — so this either fully happens or
        (on any error) nothing happens at all.
        """
        # Row lock first: a concurrent redemption of the same code blocks
        # here until this transaction commits or rolls back, then re-reads
        # status=USED and is rejected — this is what prevents double
        # redemption under a race, not just the UNUSED check by itself.
        voucher = await self.voucher_repo.get_by_code_for_update(tenant_id=tenant_id, code=code)
        if voucher is None:
            raise NotFoundError("Voucher not found")
        if voucher.status != VoucherStatus.UNUSED:
            raise ConflictError("This voucher has already been used")

        customer = await self.customer_repo.get_by_id(tenant_id=tenant_id, id=customer_id)
        if customer is None:
            raise DomainValidationError("customer_id does not belong to this tenant")

        batch = await self.batch_repo.get_by_id(tenant_id=tenant_id, id=voucher.batch_id)
        if batch is None:
            raise DomainValidationError("Voucher's batch no longer exists")

        package = await self.package_repo.get_by_id(tenant_id=tenant_id, id=batch.package_id)
        if package is None:
            raise DomainValidationError("Voucher's package no longer exists")
        if package.status != PackageStatus.ACTIVE:
            raise DomainValidationError("This package is no longer active")

        subscription_service = SubscriptionService(self.db)
        subscription = await subscription_service.create_from_voucher(
            tenant_id=tenant_id,
            actor_id=actor_id,
            customer_id=customer_id,
            package=package,
            voucher_id=voucher.id,
        )

        voucher = await self.voucher_repo.update(
            voucher,
            status=VoucherStatus.USED,
            redeemed_by_customer_id=customer_id,
            redeemed_subscription_id=subscription.id,
            redeemed_at=datetime.now(UTC),
        )

        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="voucher.redeemed",
            target_type="offline_voucher",
            target_id=voucher.id,
            metadata={"subscription_id": str(subscription.id), "customer_id": str(customer_id)},
        )

        return voucher, subscription
