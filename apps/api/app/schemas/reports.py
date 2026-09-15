from pydantic import BaseModel

from app.core.money import Money


class TenantSummaryRead(BaseModel):
    customers_total: int
    routers_total: int
    routers_online: int
    active_subscriptions: int
    transactions_total: int
    wallet_balance: Money
