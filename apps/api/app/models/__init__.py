"""SQLAlchemy models. Importing this package registers every table on
Base.metadata — required by alembic/env.py for autogenerate and by
scripts that need the full schema (e.g. `Base.metadata.create_all`).
"""

from app.models.audit import AuditLog
from app.models.finance import (
    LedgerEntry,
    PaymentWebhook,
    SettlementLog,
    TenantWallet,
    Transaction,
    Withdrawal,
    WithdrawalDestination,
)
from app.models.network import (
    Customer,
    CustomerDevice,
    Location,
    OfflineVoucher,
    Package,
    Router,
    Subscription,
    UserSession,
    VoucherBatch,
)
from app.models.onboarding import (
    EmailEvent,
    TenantFeatureFlags,
    TenantSettings,
    TenantVerification,
)
from app.models.tenancy import (
    Permission,
    Profile,
    ProfileRole,
    Role,
    RolePermission,
    Tenant,
)

__all__ = [
    "AuditLog",
    "Customer",
    "CustomerDevice",
    "EmailEvent",
    "LedgerEntry",
    "Location",
    "OfflineVoucher",
    "Package",
    "PaymentWebhook",
    "Permission",
    "Profile",
    "ProfileRole",
    "Role",
    "RolePermission",
    "Router",
    "SettlementLog",
    "Subscription",
    "Tenant",
    "TenantFeatureFlags",
    "TenantSettings",
    "TenantVerification",
    "TenantWallet",
    "Transaction",
    "UserSession",
    "VoucherBatch",
    "Withdrawal",
    "WithdrawalDestination",
]
