from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, DomainValidationError, NotFoundError
from app.core.pagination import ListParams
from app.core.phone import normalize_tz_phone
from app.models.network import Customer
from app.repositories.customers import CustomerRepository
from app.services.audit import write_audit_log


class CustomerService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = CustomerRepository(db)

    async def list(self, *, tenant_id: UUID, params: ListParams) -> tuple[list[Customer], int]:
        return await self.repo.list_paginated(tenant_id=tenant_id, params=params)

    async def get(self, *, tenant_id: UUID, customer_id: UUID) -> Customer:
        customer = await self.repo.get_by_id(tenant_id=tenant_id, id=customer_id)
        if customer is None:
            raise NotFoundError("Customer not found")
        return customer

    async def create(
        self,
        *,
        tenant_id: UUID,
        actor_id: UUID | None,
        first_name: str | None,
        last_name: str | None,
        phone: str,
        email: str | None,
        username: str | None,
        notes: str | None,
    ) -> Customer:
        try:
            normalized_phone = normalize_tz_phone(phone)
        except ValueError as exc:
            raise DomainValidationError(str(exc)) from exc

        existing = await self.repo.get_by_phone(tenant_id=tenant_id, phone=normalized_phone)
        if existing is not None:
            raise ConflictError(f"A customer with phone {normalized_phone} already exists")

        if username is not None:
            existing_username = await self.repo.get_by_username(
                tenant_id=tenant_id, username=username
            )
            if existing_username is not None:
                raise ConflictError(f"Username {username!r} is already taken")

        # Server-generated — never accepted from client input.
        customer_number = await self.repo.next_customer_number()

        customer = await self.repo.create(
            tenant_id=tenant_id,
            customer_number=customer_number,
            first_name=first_name,
            last_name=last_name,
            phone=normalized_phone,
            email=email,
            username=username,
            notes=notes,
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=actor_id,
            action="customer.created",
            target_type="customer",
            target_id=customer.id,
        )
        return customer

    async def get_or_create_by_phone(self, *, tenant_id: UUID, phone: str) -> Customer:
        """Used by the captive portal's self-service payment flow (see
        app/services/captive_portal.py) — a returning customer's existing
        record is reused rather than raising ConflictError, since the
        caller here is the anonymous customer themselves, not staff
        knowingly creating a new record."""
        try:
            normalized_phone = normalize_tz_phone(phone)
        except ValueError as exc:
            raise DomainValidationError(str(exc)) from exc

        existing = await self.repo.get_by_phone(tenant_id=tenant_id, phone=normalized_phone)
        if existing is not None:
            return existing

        customer_number = await self.repo.next_customer_number()
        customer = await self.repo.create(
            tenant_id=tenant_id,
            customer_number=customer_number,
            first_name=None,
            last_name=None,
            phone=normalized_phone,
            email=None,
            username=None,
            notes=None,
        )
        await write_audit_log(
            self.db,
            tenant_id=tenant_id,
            actor_id=None,
            action="customer.self_registered",
            target_type="customer",
            target_id=customer.id,
        )
        return customer
