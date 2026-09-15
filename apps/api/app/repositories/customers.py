from uuid import UUID

from sqlalchemy import func, select

from app.models.network import Customer, CustomerDevice
from app.repositories.base import BaseRepository


class CustomerRepository(BaseRepository[Customer]):
    model = Customer
    search_fields = ("first_name", "last_name", "phone", "email", "customer_number", "username")
    filterable_fields = ("status",)
    sortable_fields = ("created_at", "first_name", "last_name", "customer_number", "status")

    async def get_by_phone(self, *, tenant_id: UUID, phone: str) -> Customer | None:
        stmt = self._base_query(tenant_id=tenant_id).where(Customer.phone == phone)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_username(self, *, tenant_id: UUID, username: str) -> Customer | None:
        stmt = self._base_query(tenant_id=tenant_id).where(Customer.username == username)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def next_customer_number(self) -> str:
        """Atomically reserves the next customer number from a platform-wide
        Postgres sequence — concurrency-safe without any row locking, and
        never derived from a client-supplied value."""
        result = await self.db.execute(select(func.nextval("customer_number_seq")))
        sequence_value = result.scalar_one()
        return f"CUS{sequence_value:06d}"


class CustomerDeviceRepository(BaseRepository[CustomerDevice]):
    model = CustomerDevice
    search_fields = ("mac_address", "device_label")
    filterable_fields = ("customer_id",)
    sortable_fields = ("created_at",)
