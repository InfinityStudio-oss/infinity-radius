from uuid import UUID

from sqlalchemy import exists, select

from app.models.network import OfflineVoucher, Package, Subscription, VoucherBatch
from app.repositories.base import BaseRepository


class PackageRepository(BaseRepository[Package]):
    model = Package
    search_fields = ("name", "description")
    filterable_fields = ("status", "activation_type")
    sortable_fields = ("created_at", "name", "price_tzs", "status")


class SubscriptionRepository(BaseRepository[Subscription]):
    model = Subscription
    filterable_fields = ("status", "customer_id", "package_id")
    sortable_fields = ("created_at", "activated_at", "expires_at", "status")


class VoucherBatchRepository(BaseRepository[VoucherBatch]):
    model = VoucherBatch
    filterable_fields = ("package_id",)
    sortable_fields = ("created_at", "quantity")


class OfflineVoucherRepository(BaseRepository[OfflineVoucher]):
    model = OfflineVoucher
    search_fields = ("code",)
    filterable_fields = ("status", "batch_id")
    sortable_fields = ("created_at", "status")

    async def exists_by_code(self, *, tenant_id: UUID, code: str) -> bool:
        stmt = select(
            exists().where(OfflineVoucher.tenant_id == tenant_id, OfflineVoucher.code == code)
        )
        result = await self.db.execute(stmt)
        return bool(result.scalar())

    async def get_by_code_for_update(
        self, *, tenant_id: UUID, code: str
    ) -> OfflineVoucher | None:
        """Locks the voucher row (`SELECT ... FOR UPDATE`) so two concurrent
        redemption attempts for the same code serialize instead of racing —
        the second blocks until the first commits, then sees status=USED."""
        stmt = (
            self._base_query(tenant_id=tenant_id)
            .where(OfflineVoucher.code == code)
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
