"""Platform-wide (super-admin) dashboard schemas. Every field is a real
aggregation across ALL tenants — no query is fabricated, and any metric
with no real backing table yet (reconciliation_exceptions) is reported
honestly via `MetricValue.not_configured()`, matching
app.schemas.common's contract, rather than a fake zero implying "checked,
found none".
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.core.money import Money
from app.schemas.common import MetricValue


class SuperAdminSummaryRead(BaseModel):
    active_tenants: int
    suspended_tenants: int
    routers_total: int
    routers_online: int
    radius_active_sessions: int
    collections_today_tzs: Money
    pending_payouts: int
    pending_payouts_amount_tzs: Money
    failed_webhooks: int
    reconciliation_exceptions: MetricValue


class TenantGrowthPoint(BaseModel):
    date: date
    new_tenants: int


class PendingPayoutRow(BaseModel):
    withdrawal_id: UUID
    tenant_name: str
    amount_tzs: Money
    status: str
    requested_at: datetime


class ReconciliationHealthRead(BaseModel):
    """See app/services/super_admin_dashboard.py.reconciliation_health —
    entirely derived from the audit trail plus a live count. A recent
    last_run_at is the real signal that Celery Beat/Worker are alive and
    actually executing the reconciliation sweep."""

    last_run_at: datetime | None
    minutes_since_last_run: float | None
    last_scanned: int | None
    last_resolved: int | None
    last_still_pending: int | None
    last_failed: int | None
    last_alerted: int | None
    currently_processing: int
    currently_ambiguous: int
