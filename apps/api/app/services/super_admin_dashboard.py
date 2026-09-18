"""Platform-wide (super-admin) dashboard aggregation. Every method here
queries across ALL tenants — no tenant_id filter — nothing is seeded,
sampled, or randomly generated. A brand-new platform with zero tenants
legitimately gets all zeros; that is the correct answer, not a placeholder.

"Today" is computed in the platform's operating timezone
(Settings.default_timezone — Africa/Dar_es_Salaam), not UTC, matching
app.services.dashboard's tenant-scoped equivalent.
"""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import LedgerEntryType, TenantStatus, WithdrawalStatus
from app.models.audit import AuditLog
from app.models.finance import LedgerEntry, PaymentWebhook, Withdrawal
from app.models.network import Router, UserSession
from app.models.tenancy import Tenant
from app.schemas.dashboard import CollectionsTrendPoint
from app.schemas.super_admin_dashboard import PendingPayoutRow, TenantGrowthPoint

_PENDING_WITHDRAWAL_STATUSES = (
    WithdrawalStatus.PENDING_APPROVAL.value,
    WithdrawalStatus.APPROVED.value,
)


def _operating_timezone() -> ZoneInfo:
    return ZoneInfo(get_settings().default_timezone)


def _trailing_local_dates(days: int, tz: ZoneInfo) -> list[dt.date]:
    today = dt.datetime.now(tz).date()
    return [today - dt.timedelta(days=offset) for offset in range(days - 1, -1, -1)]


@dataclass(frozen=True)
class SuperAdminSummary:
    active_tenants: int
    suspended_tenants: int
    routers_total: int
    routers_online: int
    radius_active_sessions: int
    collections_today_tzs: Decimal
    pending_payouts: int
    pending_payouts_amount_tzs: Decimal
    failed_webhooks: int


@dataclass(frozen=True)
class ReconciliationHealth:
    """Derived entirely from the audit trail (the most recent
    "withdrawal.reconciliation_swept" row app/tasks/reconciliation.py
    writes every Beat cycle) plus a live count — no separate table, no
    provider secret, no Railway/Celery infrastructure query. `last_run_at`
    being recent is the real signal that Beat+Worker are alive and
    actually executing the sweep, not just deployed."""

    last_run_at: dt.datetime | None
    minutes_since_last_run: float | None
    last_scanned: int | None
    last_resolved: int | None
    last_still_pending: int | None
    last_failed: int | None
    last_alerted: int | None
    currently_processing: int
    currently_ambiguous: int


class SuperAdminDashboardService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def summary(self) -> SuperAdminSummary:
        tz = _operating_timezone()
        today_start = dt.datetime.combine(dt.datetime.now(tz).date(), dt.time.min, tzinfo=tz)

        active_tenants = await self._count(
            select(func.count()).select_from(Tenant).where(Tenant.status == TenantStatus.ACTIVE)
        )
        suspended_tenants = await self._count(
            select(func.count())
            .select_from(Tenant)
            .where(Tenant.status == TenantStatus.SUSPENDED)
        )
        routers_total = await self._count(select(func.count()).select_from(Router))
        routers_online = await self._count(
            select(func.count()).select_from(Router).where(Router.status == "online")
        )
        radius_active_sessions = await self._count(
            select(func.count()).select_from(UserSession).where(UserSession.status == "active")
        )

        collections_result = await self.db.execute(
            select(func.coalesce(func.sum(LedgerEntry.amount), 0)).where(
                LedgerEntry.entry_type == LedgerEntryType.COLLECTION.value,
                LedgerEntry.created_at >= today_start,
            )
        )
        collections_today_tzs = Decimal(collections_result.scalar_one())

        pending_result = await self.db.execute(
            select(func.count(), func.coalesce(func.sum(Withdrawal.amount), 0)).where(
                Withdrawal.status.in_(_PENDING_WITHDRAWAL_STATUSES)
            )
        )
        pending_payouts, pending_payouts_amount_tzs = pending_result.one()

        # Honest definition of "failed" given today's schema: a callback
        # that was actually run through verification and rejected — see
        # app/integrations/selcom/collection.py. Rows still sitting at
        # signature_verified=false, processed=false mean "not yet
        # verifiable" (Selcom's real signing scheme is undocumented), not
        # "failed" — counting those would overstate real failures.
        failed_webhooks = await self._count(
            select(func.count())
            .select_from(PaymentWebhook)
            .where(PaymentWebhook.signature_verified.is_(False), PaymentWebhook.processed.is_(True))
        )

        return SuperAdminSummary(
            active_tenants=active_tenants,
            suspended_tenants=suspended_tenants,
            routers_total=routers_total,
            routers_online=routers_online,
            radius_active_sessions=radius_active_sessions,
            collections_today_tzs=collections_today_tzs,
            pending_payouts=pending_payouts,
            pending_payouts_amount_tzs=Decimal(pending_payouts_amount_tzs),
            failed_webhooks=failed_webhooks,
        )

    async def collections_trend(self, *, days: int = 14) -> list[CollectionsTrendPoint]:
        tz = _operating_timezone()
        local_dates = _trailing_local_dates(days, tz)
        window_start = dt.datetime.combine(local_dates[0], dt.time.min, tzinfo=tz)

        local_day = func.date_trunc(
            "day", func.timezone(get_settings().default_timezone, LedgerEntry.created_at)
        )
        stmt = (
            select(local_day, func.sum(LedgerEntry.amount))
            .where(
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
            return []

        return [
            CollectionsTrendPoint(date=day, collections_tzs=by_day.get(day, Decimal("0")))
            for day in local_dates
        ]

    async def tenant_growth_trend(self, *, days: int = 30) -> list[TenantGrowthPoint]:
        tz = _operating_timezone()
        local_dates = _trailing_local_dates(days, tz)
        window_start = dt.datetime.combine(local_dates[0], dt.time.min, tzinfo=tz)

        local_day = func.date_trunc(
            "day", func.timezone(get_settings().default_timezone, Tenant.created_at)
        )
        stmt = (
            select(local_day, func.count())
            .select_from(Tenant)
            .where(Tenant.created_at >= window_start)
            .group_by(local_day)
        )
        result = await self.db.execute(stmt)
        by_day: dict[dt.date, int] = {
            local_midnight.date(): int(count) for local_midnight, count in result.all()
        }

        if not by_day:
            return []

        return [
            TenantGrowthPoint(date=day, new_tenants=by_day.get(day, 0)) for day in local_dates
        ]

    async def pending_payouts_queue(self, *, limit: int = 10) -> list[PendingPayoutRow]:
        stmt = (
            select(
                Withdrawal.id,
                Tenant.name,
                Withdrawal.amount,
                Withdrawal.status,
                Withdrawal.created_at,
            )
            .select_from(Withdrawal)
            .join(Tenant, Tenant.id == Withdrawal.tenant_id)
            .where(Withdrawal.status.in_(_PENDING_WITHDRAWAL_STATUSES))
            .order_by(Withdrawal.created_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [
            PendingPayoutRow(
                withdrawal_id=withdrawal_id,
                tenant_name=tenant_name,
                amount_tzs=Decimal(amount),
                status=status,
                requested_at=requested_at,
            )
            for withdrawal_id, tenant_name, amount, status, requested_at in result.all()
        ]

    async def reconciliation_health(self) -> ReconciliationHealth:
        row = (
            await self.db.execute(
                select(AuditLog.created_at, AuditLog.log_metadata)
                .where(AuditLog.action == "withdrawal.reconciliation_swept")
                .order_by(AuditLog.created_at.desc())
                .limit(1)
            )
        ).first()

        last_run_at: dt.datetime | None = None
        minutes_since: float | None = None
        metadata: dict[str, Any] = {}
        if row is not None:
            last_run_at, metadata = row
            metadata = metadata or {}
            reference = last_run_at if last_run_at.tzinfo else last_run_at.replace(tzinfo=dt.UTC)
            minutes_since = (dt.datetime.now(dt.UTC) - reference).total_seconds() / 60

        processing_count = await self._count(
            select(func.count(Withdrawal.id)).where(
                Withdrawal.status == WithdrawalStatus.PROCESSING.value
            )
        )
        ambiguous_count = await self._count(
            select(func.count(Withdrawal.id)).where(
                Withdrawal.status == WithdrawalStatus.AMBIGUOUS.value
            )
        )

        return ReconciliationHealth(
            last_run_at=last_run_at,
            minutes_since_last_run=minutes_since,
            last_scanned=metadata.get("scanned"),
            last_resolved=metadata.get("resolved"),
            last_still_pending=metadata.get("still_pending"),
            last_failed=metadata.get("failed"),
            last_alerted=metadata.get("alerted"),
            currently_processing=processing_count,
            currently_ambiguous=ambiguous_count,
        )

    async def _count(self, stmt: Select[Any]) -> int:
        result = await self.db.execute(stmt)
        return int(result.scalar_one())
