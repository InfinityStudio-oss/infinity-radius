"""business modules: customers, packages, subscriptions, vouchers

Revision ID: eafef8056e3d
Revises: 41619a38de4a
Create Date: 2026-09-13 09:00:00.000000

Real fields for the four core business modules:

- customers: server-generated customer_number (via a Postgres sequence —
  never client-supplied), first_name/last_name (replacing full_name),
  username, notes.
- packages: price_tzs (replacing price+currency — always TZS), bytes_limit,
  download_speed_kbps/upload_speed_kbps (renamed from speed_down/up_kbps),
  simultaneous_sessions, activation_type, status (replacing is_active).
- subscriptions: voucher_id (which voucher activated it, if any),
  activated_at/expires_at (renamed from starts_at/ends_at), bytes_used, and
  an expanded uppercase status vocabulary (PENDING/ACTIVE/EXPIRED/
  SUSPENDED/CANCELLED/QUOTA_EXCEEDED).
- offline_vouchers: redeemed_subscription_id, and an uppercase status
  vocabulary (UNUSED/USED/EXPIRED/VOID) matching subscriptions.

Any pre-existing rows (dev/test data only — nothing production-real exists
yet) are backfilled so the new NOT NULL constraints can be applied; no
sample/fake values are introduced by this migration itself.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "eafef8056e3d"
down_revision: str | None = "41619a38de4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------------------------------------------- customers
    op.execute("CREATE SEQUENCE IF NOT EXISTS customer_number_seq")

    op.add_column("customers", sa.Column("customer_number", sa.Text(), nullable=True))
    op.add_column("customers", sa.Column("first_name", sa.Text(), nullable=True))
    op.add_column("customers", sa.Column("last_name", sa.Text(), nullable=True))
    op.add_column("customers", sa.Column("username", sa.Text(), nullable=True))
    op.add_column("customers", sa.Column("notes", sa.Text(), nullable=True))

    op.execute(
        """
        UPDATE customers
        SET customer_number = 'CUS' || lpad(nextval('customer_number_seq')::text, 6, '0'),
            first_name = COALESCE(NULLIF(split_part(full_name, ' ', 1), ''), 'Unknown'),
            last_name = COALESCE(
                NULLIF(substr(full_name, length(split_part(full_name, ' ', 1)) + 2), ''),
                'Customer'
            )
        WHERE customer_number IS NULL
        """
    )

    op.alter_column("customers", "customer_number", nullable=False)
    op.alter_column("customers", "first_name", nullable=False)
    op.alter_column("customers", "last_name", nullable=False)
    op.create_unique_constraint(
        "uq_customers_tenant_customer_number", "customers", ["tenant_id", "customer_number"]
    )
    op.create_unique_constraint(
        "uq_customers_tenant_username", "customers", ["tenant_id", "username"]
    )
    op.drop_column("customers", "full_name")

    # ----------------------------------------------------------------- packages
    op.alter_column("packages", "price", new_column_name="price_tzs")
    op.alter_column("packages", "speed_down_kbps", new_column_name="download_speed_kbps")
    op.alter_column("packages", "speed_up_kbps", new_column_name="upload_speed_kbps")
    op.add_column("packages", sa.Column("bytes_limit", sa.BigInteger(), nullable=True))
    op.add_column(
        "packages",
        sa.Column("simultaneous_sessions", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "packages",
        sa.Column("activation_type", sa.Text(), nullable=False, server_default="immediate"),
    )
    op.add_column(
        "packages", sa.Column("status", sa.Text(), nullable=False, server_default="active")
    )
    op.execute("UPDATE packages SET status = CASE WHEN is_active THEN 'active' ELSE 'archived' END")
    op.drop_column("packages", "is_active")
    op.drop_column("packages", "currency")

    # ------------------------------------------------------------ subscriptions
    op.add_column(
        "subscriptions",
        sa.Column(
            "voucher_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("offline_vouchers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.alter_column("subscriptions", "starts_at", new_column_name="activated_at")
    op.alter_column("subscriptions", "ends_at", new_column_name="expires_at")
    op.add_column(
        "subscriptions",
        sa.Column("bytes_used", sa.BigInteger(), nullable=False, server_default="0"),
    )
    op.execute("UPDATE subscriptions SET status = upper(status)")
    op.alter_column("subscriptions", "status", server_default="PENDING")

    # --------------------------------------------------------------- vouchers
    op.add_column(
        "offline_vouchers",
        sa.Column(
            "redeemed_subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.execute("UPDATE offline_vouchers SET status = upper(status)")
    op.alter_column("offline_vouchers", "status", server_default="UNUSED")


def downgrade() -> None:
    op.alter_column("offline_vouchers", "status", server_default="unused")
    op.execute("UPDATE offline_vouchers SET status = lower(status)")
    op.drop_column("offline_vouchers", "redeemed_subscription_id")

    op.alter_column("subscriptions", "status", server_default="pending")
    op.execute("UPDATE subscriptions SET status = lower(status)")
    op.drop_column("subscriptions", "bytes_used")
    op.alter_column("subscriptions", "expires_at", new_column_name="ends_at")
    op.alter_column("subscriptions", "activated_at", new_column_name="starts_at")
    op.drop_column("subscriptions", "voucher_id")

    op.add_column(
        "packages", sa.Column("currency", sa.String(3), nullable=False, server_default="TZS")
    )
    op.add_column(
        "packages", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true")
    )
    op.execute("UPDATE packages SET is_active = (status = 'active')")
    op.drop_column("packages", "status")
    op.drop_column("packages", "activation_type")
    op.drop_column("packages", "simultaneous_sessions")
    op.drop_column("packages", "bytes_limit")
    op.alter_column("packages", "upload_speed_kbps", new_column_name="speed_up_kbps")
    op.alter_column("packages", "download_speed_kbps", new_column_name="speed_down_kbps")
    op.alter_column("packages", "price_tzs", new_column_name="price")

    op.add_column("customers", sa.Column("full_name", sa.Text(), nullable=True))
    op.execute("UPDATE customers SET full_name = first_name || ' ' || last_name")
    op.drop_constraint("uq_customers_tenant_username", "customers", type_="unique")
    op.drop_constraint("uq_customers_tenant_customer_number", "customers", type_="unique")
    op.drop_column("customers", "notes")
    op.drop_column("customers", "username")
    op.drop_column("customers", "last_name")
    op.drop_column("customers", "first_name")
    op.drop_column("customers", "customer_number")
    op.execute("DROP SEQUENCE IF EXISTS customer_number_seq")
