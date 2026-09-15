"""Generic repository: the only layer that issues SQL. Every entity
repository is a thin subclass declaring its model plus which columns are
searchable/filterable/sortable — see app/repositories/*.py for examples.

Tenant scoping is enforced here, not trusted from callers: every method
takes `tenant_id` explicitly (None only for platform-wide/reference
tables that have no tenant_id column at all) and applies it as a WHERE
clause whenever the model has a `tenant_id` column, so a service simply
cannot forget to scope a query.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pagination import ListParams
from app.db.base import Base


class BaseRepository[ModelType: Base]:
    model: type[ModelType]
    search_fields: tuple[str, ...] = ()
    filterable_fields: tuple[str, ...] = ()
    sortable_fields: tuple[str, ...] = ("created_at",)
    default_sort: str = "-created_at"

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _base_query(self, *, tenant_id: UUID | None) -> Select[Any]:
        stmt = select(self.model)
        if tenant_id is not None and hasattr(self.model, "tenant_id"):
            stmt = stmt.where(self.model.tenant_id == tenant_id)  # type: ignore[attr-defined]
        return stmt

    async def get_by_id(self, *, tenant_id: UUID | None, id: UUID) -> ModelType | None:
        stmt = self._base_query(tenant_id=tenant_id).where(self.model.id == id)  # type: ignore[attr-defined]
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, *, tenant_id: UUID | None, id: UUID) -> ModelType | None:
        """Same as get_by_id, but takes a `SELECT ... FOR UPDATE` row lock —
        held until the caller's transaction commits/rolls back — so a
        concurrent request touching the same row blocks instead of racing
        with it. Use only inside a flow that ends in one commit (never call
        this and then return without committing/rolling back promptly)."""
        stmt = (
            self._base_query(tenant_id=tenant_id)
            .where(self.model.id == id)  # type: ignore[attr-defined]
            .with_for_update()
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_paginated(
        self, *, tenant_id: UUID | None, params: ListParams
    ) -> tuple[list[ModelType], int]:
        stmt = self._base_query(tenant_id=tenant_id)

        if params.search and self.search_fields:
            pattern = f"%{params.search}%"
            conditions = [
                getattr(self.model, field_name).ilike(pattern) for field_name in self.search_fields
            ]
            stmt = stmt.where(or_(*conditions))

        for key, value in params.filters.items():
            if key in self.filterable_fields and hasattr(self.model, key):
                stmt = stmt.where(getattr(self.model, key) == value)

        total = await self._count(stmt)

        sort_spec = params.sort or self.default_sort
        descending = sort_spec.startswith("-")
        column_name = sort_spec.removeprefix("-")
        if column_name in self.sortable_fields and hasattr(self.model, column_name):
            column = getattr(self.model, column_name)
            stmt = stmt.order_by(column.desc() if descending else column.asc())

        stmt = stmt.offset(params.offset).limit(params.page_size)
        result = await self.db.execute(stmt)
        return list(result.scalars().all()), total

    async def _count(self, stmt: Select[Any]) -> int:
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        result = await self.db.execute(count_stmt)
        return result.scalar_one()

    async def create(self, **values: Any) -> ModelType:
        obj = self.model(**values)
        self.db.add(obj)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def update(self, obj: ModelType, **values: Any) -> ModelType:
        for key, value in values.items():
            setattr(obj, key, value)
        await self.db.flush()
        await self.db.refresh(obj)
        return obj

    async def delete(self, obj: ModelType) -> None:
        await self.db.delete(obj)
        await self.db.flush()
