"""initial schema

Revision ID: 78bb02eec08a
Revises:
Create Date: 2026-09-12 21:54:43.725030

Creates every table for the tenancy/RBAC/network/billing/finance/audit
schema. No RLS, no functions, no seed data — see the two migrations that
follow (rbac_seed_data, rls_policies). No fake/sample rows are inserted
here; every table starts and stays empty until real tenants create data.

`auth.users` is NOT created here — it is owned and managed by Supabase
Auth. `profiles.id` references it by name only; the FK is created against
whatever `auth.users` already exists in the target database.
"""

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "78bb02eec08a"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_pk() -> sa.Column[Any]:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )


def _timestamps() -> list[sa.Column[Any]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def _created_at() -> sa.Column[Any]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.text("now()"),
        nullable=False,
    )


# Every table that gets an updated_at trigger (i.e. every table with an
# updated_at column, via TimestampMixin).
TABLES_WITH_UPDATED_AT = [
    "tenants",
    "profiles",
    "profile_roles",
    "locations",
    "routers",
    "packages",
    "customers",
    "customer_devices",
    "subscriptions",
    "transactions",
    "tenant_wallets",
    "withdrawals",
]


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # --- Tenancy & RBAC -----------------------------------------------
    op.create_table(
        "tenants",
        _uuid_pk(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("country", sa.Text(), nullable=False, server_default="Tanzania"),
        sa.Column("currency", sa.String(3), nullable=False, server_default="TZS"),
        sa.Column(
            "timezone", sa.Text(), nullable=False, server_default="Africa/Dar_es_Salaam"
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        *_timestamps(),
    )

    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="invited"),
        *_timestamps(),
    )
    # profiles.id references auth.users.id (Supabase-managed schema/table,
    # not created by this migration).
    op.execute(
        "ALTER TABLE public.profiles "
        "ADD CONSTRAINT profiles_id_fkey "
        "FOREIGN KEY (id) REFERENCES auth.users (id) ON DELETE CASCADE"
    )
    op.create_index("ix_profiles_tenant_id", "profiles", ["tenant_id"])

    op.create_table(
        "roles",
        _uuid_pk(),
        sa.Column("code", sa.String(32), nullable=False, unique=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.create_table(
        "permissions",
        _uuid_pk(),
        sa.Column("code", sa.String(128), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
    )

    op.create_table(
        "role_permissions",
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "permission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "profile_roles",
        _uuid_pk(),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=True,
        ),
        *_timestamps(),
        sa.UniqueConstraint("profile_id", "role_id", "tenant_id"),
    )
    op.create_index("ix_profile_roles_profile_id", "profile_roles", ["profile_id"])
    op.create_index("ix_profile_roles_tenant_id", "profile_roles", ["tenant_id"])

    # --- Network / billing catalog / subscribers -----------------------
    op.create_table(
        "locations",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column(
            "timezone", sa.Text(), nullable=False, server_default="Africa/Dar_es_Salaam"
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        *_timestamps(),
    )
    op.create_index("ix_locations_tenant_id", "locations", ["tenant_id"])

    op.create_table(
        "routers",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "location_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("locations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("serial_number", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column("management_ip", sa.Text(), nullable=True),
        sa.Column("mac_address", sa.Text(), nullable=True),
        sa.Column("firmware_version", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="unknown"),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_routers_tenant_id", "routers", ["tenant_id"])

    op.create_table(
        "packages",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("price", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="TZS"),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("speed_down_kbps", sa.Integer(), nullable=True),
        sa.Column("speed_up_kbps", sa.Integer(), nullable=True),
        sa.Column("device_limit", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        *_timestamps(),
    )
    op.create_index("ix_packages_tenant_id", "packages", ["tenant_id"])

    op.create_table(
        "customers",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "phone"),
    )
    op.create_index("ix_customers_tenant_id", "customers", ["tenant_id"])

    op.create_table(
        "customer_devices",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mac_address", sa.Text(), nullable=False),
        sa.Column("device_label", sa.Text(), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "mac_address"),
    )
    op.create_index("ix_customer_devices_tenant_id", "customer_devices", ["tenant_id"])
    op.create_index("ix_customer_devices_customer_id", "customer_devices", ["customer_id"])

    op.create_table(
        "subscriptions",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "package_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("packages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_subscriptions_tenant_id", "subscriptions", ["tenant_id"])
    op.create_index("ix_subscriptions_customer_id", "subscriptions", ["customer_id"])

    op.create_table(
        "user_sessions",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "router_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("routers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "device_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customer_devices.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("session_identifier", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("bytes_in", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("bytes_out", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        _created_at(),
    )
    op.create_index("ix_user_sessions_tenant_id", "user_sessions", ["tenant_id"])
    op.create_index("ix_user_sessions_customer_id", "user_sessions", ["customer_id"])
    op.create_index("ix_user_sessions_router_id", "user_sessions", ["router_id"])

    op.create_table(
        "voucher_batches",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "package_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("packages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("prefix", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        _created_at(),
    )
    op.create_index("ix_voucher_batches_tenant_id", "voucher_batches", ["tenant_id"])

    op.create_table(
        "offline_vouchers",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "batch_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("voucher_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="unused"),
        sa.Column(
            "redeemed_by_customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
        sa.UniqueConstraint("tenant_id", "code"),
    )
    op.create_index("ix_offline_vouchers_tenant_id", "offline_vouchers", ["tenant_id"])
    op.create_index("ix_offline_vouchers_batch_id", "offline_vouchers", ["batch_id"])

    # --- Finance ---------------------------------------------------------
    op.create_table(
        "transactions",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "customer_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reference", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="TZS"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        *_timestamps(),
        sa.UniqueConstraint("tenant_id", "reference"),
    )
    op.create_index("ix_transactions_tenant_id", "transactions", ["tenant_id"])
    op.create_index("ix_transactions_customer_id", "transactions", ["customer_id"])

    op.create_table(
        "payment_webhooks",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("provider", sa.Text(), nullable=False, server_default="selcom"),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "signature_verified", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("processed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_payment_webhooks_tenant_id", "payment_webhooks", ["tenant_id"])

    op.create_table(
        "tenant_wallets",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("currency", sa.String(3), nullable=False, server_default="TZS"),
        sa.Column("balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
        *_timestamps(),
    )

    op.create_table(
        "ledger_entries",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "wallet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant_wallets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_type", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("balance_after", sa.Numeric(14, 2), nullable=True),
        sa.Column("reference_type", sa.Text(), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        _created_at(),
    )
    op.create_index("ix_ledger_entries_tenant_id", "ledger_entries", ["tenant_id"])
    op.create_index("ix_ledger_entries_wallet_id", "ledger_entries", ["wallet_id"])

    op.create_table(
        "settlement_logs",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("batch_reference", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("transaction_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("fee_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        _created_at(),
    )
    op.create_index("ix_settlement_logs_tenant_id", "settlement_logs", ["tenant_id"])

    op.create_table(
        "withdrawal_destinations",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("account_name", sa.Text(), nullable=True),
        sa.Column("account_number", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
        _created_at(),
    )
    op.create_index(
        "ix_withdrawal_destinations_tenant_id", "withdrawal_destinations", ["tenant_id"]
    )

    op.create_table(
        "withdrawals",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "wallet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenant_wallets.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "destination_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("withdrawal_destinations.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="TZS"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column(
            "requested_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "approved_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        *_timestamps(),
    )
    op.create_index("ix_withdrawals_tenant_id", "withdrawals", ["tenant_id"])

    # --- Audit -------------------------------------------------------------
    op.create_table(
        "audit_logs",
        _uuid_pk(),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "actor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_type", sa.Text(), nullable=True),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        _created_at(),
    )
    op.create_index("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])

    # --- updated_at trigger, applied to every table that has the column ---
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.set_updated_at()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          NEW.updated_at = now();
          RETURN NEW;
        END;
        $$
        """
    )
    for table_name in TABLES_WITH_UPDATED_AT:
        op.execute(
            f"""
            CREATE TRIGGER set_updated_at
            BEFORE UPDATE ON public.{table_name}
            FOR EACH ROW
            EXECUTE FUNCTION public.set_updated_at()
            """
        )


def downgrade() -> None:
    for table_name in TABLES_WITH_UPDATED_AT:
        op.execute(f"DROP TRIGGER IF EXISTS set_updated_at ON public.{table_name}")
    op.execute("DROP FUNCTION IF EXISTS public.set_updated_at()")

    for table_name in [
        "audit_logs",
        "withdrawals",
        "withdrawal_destinations",
        "settlement_logs",
        "ledger_entries",
        "tenant_wallets",
        "payment_webhooks",
        "transactions",
        "offline_vouchers",
        "voucher_batches",
        "user_sessions",
        "subscriptions",
        "customer_devices",
        "customers",
        "packages",
        "routers",
        "locations",
        "profile_roles",
        "role_permissions",
        "permissions",
        "roles",
        "profiles",
        "tenants",
    ]:
        op.drop_table(table_name)
