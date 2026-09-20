"""Tenant dashboard landing-page aggregation. Every method here is a real
query against the tenant's own rows — nothing is seeded, sampled, or
randomly generated. An empty/new tenant legitimately gets zeros and empty
lists; that is the correct answer, not a placeholder.

"Today" is computed in the platform's operating timezone
(Settings.default_timezone — Africa/Dar_es_Salaam, Tanzania being the only
market this runs in today), not UTC, so a day boundary lines up with when
a Tanzanian operator actually experiences "today".
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import (
    COLLECTION_TERMINAL_STATUSES,
    CollectionStatus,
    LedgerEntryType,
    VoucherStatus,
)
from app.models.finance import LedgerEntry, TenantWallet, Transaction
from app.models.network import OfflineVoucher, Package, Router, Subscription, UserSession
from app.schemas.dashboard import CollectionsTrendPoint, PackagePerformanceRow, SessionTrendPoint


def _operating_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().default_timezone)


def _trailing_local_dates(days: int, tz: ZoneInfo) -> list[dt.date]:
    today = dt.datetime.now(tz).date()
    return [today - dt.timedelta(days=offset) for offset in range(days - 1, -1, -1)]


@dataclass(frozen=True)
class DashboardSummary:
    online_users: int
    today_collections_tzs: Decimal
    active_vouchers: int
    routers_online: int
    routers_total: int
    failed_transactions: int
    available_wallet_balance_tzs: Decimal


# Terminal-but-unsuccessful transaction statuses — one definition shared
# with reconciliation (COLLECTION_TERMINAL_STATUSES) so a newly added
# status cannot silently drop out of the operational "failed today" count.
_FAILED_TRANSACTION_STATUSES = frozenset(
    status.value
    for status in COLLECTION_TERMINAL_STATUSES
    if status is not CollectionStatus.COMPLETED
)


class DashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def summary(self, *, tenant_id: UUID) -> DashboardSummary:
        tz = _operating_timezone()
        today_start = dt.datetime.combine(dt.datetime.now(tz).date(), dt.time.min, tzinfo=tz)

        online_users = await self._count(
            select(func.count())
            .select_from(UserSession)
            .where(UserSession.tenant_id == tenant_id, UserSession.status == "active")
        )

        today_collections_result = await self.db.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.tenant_id == tenant_id,
                LedgerEntry.entry_type == LedgerEntryType.COLLECTION.value,
                LedgerEntry.created_at >= today_start,
            )
        )
        today_collections_tzs = Decimal(today_collections_result.scalar_one())

        active_vouchers = await self._count(
            select(func.count())
            .select_from(OfflineVoucher)
            .where(
                OfflineVoucher.tenant_id == tenant_id,
                OfflineVoucher.status == VoucherStatus.UNUSED.value,
            )
        )

        routers_total = await self._count(
            select(func.count()).select_from(Router).where(Router.tenant_id == tenant_id)
        )
        routers_online = await self._count(
            select(func.count())
            .select_from(Router)
            .where(Router.tenant_id == tenant_id, Router.status == "online")
        )

        # Paired with today_collections_tzs as a same-day operational
        # snapshot, not an all-time count — a growing all-time total would
        # stop being a useful "is something wrong right now" signal.
        failed_transactions = await self._count(
            select(func.count())
            .select_from(Transaction)
            .where(
                Transaction.tenant_id == tenant_id,
                # Every terminal-but-not-successful status, from the same
                # definition reconciliation uses. This previously compared
                # against a lowercase "failed" that NO writer has produced
                # since Collection landed, so the count was always 0 — and
                # unifying captive-portal statuses onto CollectionStatus
                # would have made it permanently 0 for both families.
                Transaction.status.in_(_FAILED_TRANSACTION_STATUSES),
                Transaction.created_at >= today_start,
            )
        )

        wallet_result = await self.db.execute(
            select(TenantWallet.available_balance_tzs).where(TenantWallet.tenant_id == tenant_id)
        )
        wallet_balance = wallet_result.scalar_one_or_none()

        return DashboardSummary(
            online_users=online_users,
            today_collections_tzs=today_collections_tzs,
            active_vouchers=active_vouchers,
            routers_online=routers_online,
            routers_total=routers_total,
            failed_transactions=failed_transactions,
            available_wallet_balance_tzs=(
                Decimal(wallet_balance) if wallet_balance is not None else Decimal("0")
            ),
        )

    async def collections_trend(
        self, *, tenant_id: UUID, days: int = 14
    ) -> list[CollectionsTrendPoint]:
        tz = _operating_timezone()
        local_dates = _trailing_local_dates(days, tz)
        window_start = dt.datetime.combine(local_dates[0], dt.time.min, tzinfo=tz)

        local_day = func.date_trunc(
            "day", func.timezone(get_settings().default_timezone, LedgerEntry.created_at)
        )
        stmt = (
            select(local_day, func.sum(LedgerEntry.amount))
            .where(
                LedgerEntry.tenant_id == tenant_id,
                LedgerEntry.entry_type == LedgerEntryType.COLLECTION.value,
                LedgerEntry.created_at >= window_start,
            )
            .group_by(local_day)
        )
        result = await self.db.execute(stmt)
        by_day: dict[dt.date, Decimal] = {
            local_midnight.date(): Decimal(total) for local_midnight, total in result.all()
        }

        if not by_day:
            # No collection activity at all in the window — an honest empty
            # chart, never a fabricated flat/zero line drawn just to fill space.
            return []

        return [
            CollectionsTrendPoint(date=day, collections_tzs=by_day.get(day, Decimal("0")))
            for day in local_dates
        ]

    async def session_trend(self, *, tenant_id: UUID, days: int = 14) -> list[SessionTrendPoint]:
        tz = _operating_timezone()
        local_dates = _trailing_local_dates(days, tz)
        window_start = dt.datetime.combine(local_dates[0], dt.time.min, tzinfo=tz)

        session_moment = func.coalesce(UserSession.started_at, UserSession.created_at)
        local_day = func.date_trunc(
            "day", func.timezone(get_settings().default_timezone, session_moment)
        )
        stmt = (
            select(local_day, func.count())
            .select_from(UserSession)
            .where(UserSession.tenant_id == tenant_id, session_moment >= window_start)
            .group_by(local_day)
        )
        result = await self.db.execute(stmt)
        by_day: dict[dt.date, int] = {
            local_midnight.date(): int(count) for local_midnight, count in result.all()
        }

        if not by_day:
            return []

        return [
            SessionTrendPoint(date=day, session_count=by_day.get(day, 0)) for day in local_dates
        ]

    async def package_performance(self, *, tenant_id: UUID) -> list[PackagePerformanceRow]:
        active_count = func.count(Subscription.id).filter(Subscription.status == "ACTIVE")
        # Uppercase COMPLETED, matching what both writers actually store.
        # The previous lowercase comparison matched nothing, so per-package
        # revenue silently reported 0 for every package.
        revenue = func.coalesce(
            func.sum(Transaction.amount).filter(
                Transaction.status == CollectionStatus.COMPLETED.value
            ),
            0,
        )

        stmt = (
            select(
                Package.id,
                Package.name,
                func.count(Subscription.id),
                active_count,
                revenue,
            )
            .select_from(Package)
            .outerjoin(
                Subscription,
                (Subscription.package_id == Package.id)
                & (Subscription.tenant_id == Package.tenant_id),
            )
            .outerjoin(
                Transaction,
                (Transaction.subscription_id == Subscription.id)
                & (Transaction.tenant_id == Package.tenant_id),
            )
            .where(Package.tenant_id == tenant_id)
            .group_by(Package.id, Package.name)
            .order_by(revenue.desc())
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        total_subscriptions = sum(row[2] for row in rows)
        if total_subscriptions == 0:
            # Packages may exist, but nothing has ever been sold against
            # them — that is "no package activity yet", not a table of zeros.
            return []

        return [
            PackagePerformanceRow(
                package_id=package_id,
                package_name=name,
                total_subscriptions=total_subs,
                active_subscriptions=active_subs,
                revenue_tzs=Decimal(rev),
            )
            for package_id, name, total_subs, active_subs, rev in rows
        ]

    async def _count(self, stmt: Select[Any]) -> int:
        result = await self.db.execute(stmt)
        return int(result.scalar_one())
