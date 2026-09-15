from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SubscriptionStatus
from app.models.finance import TenantWallet, Transaction
from app.models.network import Customer, Router, Subscription


@dataclass(frozen=True)
class TenantSummary:
    """Every field is a real COUNT(*)/SUM() against this tenant's own
    rows — legitimately 0 on an empty tenant, never a placeholder."""

    customers_total: int
    routers_total: int
    routers_online: int
    active_subscriptions: int
    transactions_total: int
    wallet_balance: str


class ReportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def tenant_summary(self, *, tenant_id: UUID) -> TenantSummary:
        customers_total = await self._count(
            select(func.count()).select_from(Customer).where(Customer.tenant_id == tenant_id)
        )
        routers_total = await self._count(
            select(func.count()).select_from(Router).where(Router.tenant_id == tenant_id)
        )
        routers_online = await self._count(
            select(func.count())
            .select_from(Router)
            .where(Router.tenant_id == tenant_id, Router.status == "online")
        )
        active_subscriptions = await self._count(
            select(func.count())
            .select_from(Subscription)
            .where(
                Subscription.tenant_id == tenant_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
            )
        )
        transactions_total = await self._count(
            select(func.count())
            .select_from(Transaction)
            .where(Transaction.tenant_id == tenant_id)
        )

        # Current total the tenant holds across the platform — available +
        # pending + reserved + frozen. Excludes total_disbursed_tzs, which
        # is a lifetime counter of money already paid out, not a balance.
        wallet_balance_stmt = select(
            TenantWallet.available_balance_tzs
            + TenantWallet.pending_balance_tzs
            + TenantWallet.reserved_balance_tzs
            + TenantWallet.frozen_balance_tzs
        ).where(TenantWallet.tenant_id == tenant_id)
        wallet_balance_result = await self.db.execute(wallet_balance_stmt)
        wallet_balance = wallet_balance_result.scalar_one_or_none()

        return TenantSummary(
            customers_total=customers_total,
            routers_total=routers_total,
            routers_online=routers_online,
            active_subscriptions=active_subscriptions,
            transactions_total=transactions_total,
            wallet_balance=str(wallet_balance) if wallet_balance is not None else "0.00",
        )

    async def _count(self, stmt: Select[Any]) -> int:
        result = await self.db.execute(stmt)
        return int(result.scalar_one())
