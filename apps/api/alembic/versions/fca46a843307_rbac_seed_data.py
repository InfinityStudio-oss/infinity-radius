"""rbac seed data

Revision ID: fca46a843307
Revises: 78bb02eec08a
Create Date: 2026-09-12 21:59:27.779814

Seeds the IMMUTABLE system role/permission catalog only — see
app.core.roles.Role for the Python mirror of these role codes. This is
reference/system data, not operational data: no tenants, profiles,
routers, customers, or any business row is ever created by a migration.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "fca46a843307"
down_revision: str | None = "78bb02eec08a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ROLES: list[tuple[str, str, str]] = [
    ("SUPER_ADMIN", "Super Admin", "Platform operator with full cross-tenant access."),
    ("TENANT_OWNER", "Tenant Owner", "Full control over a single tenant, including payouts."),
    ("TENANT_ADMIN", "Tenant Admin", "Day-to-day tenant administration."),
    ("ACCOUNTANT", "Accountant", "Tenant finance, billing, and reporting."),
    ("NETWORK_TECHNICIAN", "Network Technician", "Tenant network/router operations."),
    ("CUSTOMER_CARE", "Customer Care", "Tenant customer support and voucher issuance."),
    ("CASHIER", "Cashier", "Tenant point-of-sale voucher/payment operations."),
    ("CUSTOMER", "Customer", "End-customer self-service (portal auth added in a later phase)."),
]

PERMISSIONS: list[tuple[str, str]] = [
    ("platform.tenants.manage", "Create, suspend, and configure tenants."),
    ("platform.settings.manage", "Manage platform-wide configuration."),
    ("platform.audit.view", "View the platform-wide audit trail."),
    ("tenant.settings.manage", "Manage this tenant's profile and configuration."),
    ("tenant.staff.manage", "Invite and manage this tenant's staff accounts."),
    ("customers.view", "View customer records."),
    ("customers.manage", "Create and edit customer records."),
    ("network.locations.manage", "Create and edit hotspot site locations."),
    ("network.routers.manage", "Register and configure routers."),
    ("network.sessions.view", "View connectivity sessions."),
    ("billing.packages.manage", "Create and edit WiFi access packages."),
    ("billing.subscriptions.manage", "Create and edit customer subscriptions."),
    ("billing.vouchers.manage", "Generate and redeem offline vouchers."),
    ("finance.payments.view", "View customer payment transactions."),
    ("finance.wallet.view", "View the tenant wallet balance and ledger."),
    ("finance.withdrawals.request", "Request a payout from the tenant wallet."),
    ("finance.withdrawals.approve", "Approve a requested payout."),
    ("finance.reconciliation.view", "View settlement/reconciliation reports."),
    ("reports.view", "View operational and financial reports."),
    ("support.manage", "Manage customer support tickets."),
    ("audit.view", "View this tenant's audit trail."),
]

# Role code -> permission codes granted.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "SUPER_ADMIN": [
        "platform.tenants.manage",
        "platform.settings.manage",
        "platform.audit.view",
    ],
    "TENANT_OWNER": [
        "tenant.settings.manage",
        "tenant.staff.manage",
        "customers.view",
        "customers.manage",
        "network.locations.manage",
        "network.routers.manage",
        "network.sessions.view",
        "billing.packages.manage",
        "billing.subscriptions.manage",
        "billing.vouchers.manage",
        "finance.payments.view",
        "finance.wallet.view",
        "finance.withdrawals.request",
        "finance.withdrawals.approve",
        "finance.reconciliation.view",
        "reports.view",
        "support.manage",
        "audit.view",
    ],
    "TENANT_ADMIN": [
        "tenant.staff.manage",
        "customers.view",
        "customers.manage",
        "network.locations.manage",
        "network.routers.manage",
        "network.sessions.view",
        "billing.packages.manage",
        "billing.subscriptions.manage",
        "billing.vouchers.manage",
        "finance.payments.view",
        "finance.wallet.view",
        "finance.withdrawals.request",
        "finance.reconciliation.view",
        "reports.view",
        "support.manage",
        "audit.view",
    ],
    "ACCOUNTANT": [
        "customers.view",
        "billing.subscriptions.manage",
        "finance.payments.view",
        "finance.wallet.view",
        "finance.withdrawals.request",
        "finance.reconciliation.view",
        "reports.view",
    ],
    "NETWORK_TECHNICIAN": [
        "customers.view",
        "network.locations.manage",
        "network.routers.manage",
        "network.sessions.view",
    ],
    "CUSTOMER_CARE": [
        "customers.view",
        "customers.manage",
        "network.sessions.view",
        "billing.vouchers.manage",
        "support.manage",
    ],
    "CASHIER": [
        "customers.view",
        "billing.vouchers.manage",
        "finance.payments.view",
    ],
    "CUSTOMER": [],
}


def upgrade() -> None:
    conn = op.get_bind()

    for code, name, description in ROLES:
        conn.execute(
            sa.text(
                "INSERT INTO public.roles (code, name, description, is_system) "
                "VALUES (:code, :name, :description, true)"
            ),
            {"code": code, "name": name, "description": description},
        )

    for code, description in PERMISSIONS:
        conn.execute(
            sa.text(
                "INSERT INTO public.permissions (code, description) "
                "VALUES (:code, :description)"
            ),
            {"code": code, "description": description},
        )

    for role_code, permission_codes in ROLE_PERMISSIONS.items():
        for permission_code in permission_codes:
            conn.execute(
                sa.text(
                    """
                    INSERT INTO public.role_permissions (role_id, permission_id)
                    SELECT r.id, p.id
                    FROM public.roles r, public.permissions p
                    WHERE r.code = :role_code AND p.code = :permission_code
                    """
                ),
                {"role_code": role_code, "permission_code": permission_code},
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM public.role_permissions"))
    conn.execute(sa.text("DELETE FROM public.permissions"))
    conn.execute(sa.text("DELETE FROM public.roles"))
