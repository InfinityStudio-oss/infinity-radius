"""Tenant dashboard landing-page schemas. Every field here is a real
COUNT()/SUM() against the tenant's own rows (app/services/dashboard.py) —
legitimately 0 on an empty tenant, never a placeholder or sample value.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.core.money import Money


class DashboardSummaryRead(BaseModel):
    online_users: int
    today_collections_tzs: Money
    active_vouchers: int
    routers_online: int
    routers_total: int
    failed_transactions: int
    available_wallet_balance_tzs: Money


class CollectionsTrendPoint(BaseModel):
    date: date
    collections_tzs: Money


class SessionTrendPoint(BaseModel):
    date: date
    session_count: int


class PackagePerformanceRow(BaseModel):
    package_id: UUID
    package_name: str
    active_subscriptions: int
    total_subscriptions: int
    revenue_tzs: Money
