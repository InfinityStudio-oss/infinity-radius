"""production-grade tenant finance accounting

Revision ID: 02afe6ac6800
Revises: 52e3073aaba9
Create Date: 2026-09-17 09:00:00.000000

- tenant_wallets: replaces the single `balance` column with five buckets
  (available/pending/reserved/frozen/total_disbursed) — a summarized
  CURRENT-STATE view only. ledger_entries remains the source of truth;
  nothing computes a balance from the frontend, and nothing lets an admin
  type a new balance directly — see app/services/wallet.py.
- ledger_entries: entry_type gains a CHECK constraint against the real
  vocabulary (COLLECTION/TENANT_SHARE/PLATFORM_FEE/REFUND/REVERSAL/
  DISBURSEMENT/DISBURSEMENT_REVERSAL/ADJUSTMENT), plus `direction`
  (credit/debit), `wallet_bucket` (which of the five buckets moved, null
  for entries that don't move a tenant bucket at all — PLATFORM_FEE, the
  informational COLLECTION record), and `actor_id` (who caused it — null
  for system-generated entries).
- tenant_commercial_terms: a new table. Commission is never hard-coded —
  each tenant's platform commission rate is its own row here, versioned
  (old rows are deactivated, never edited), with exactly one active row
  per tenant enforced by a partial unique index.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "02afe6ac6800"
down_revision: str | None = "52e3073aaba9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------------------------------------------- wallets
    op.add_column(
        "tenant_wallets",
        sa.Column(
            "available_balance_tzs", sa.Numeric(14, 2), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "tenant_wallets",
        sa.Column("pending_balance_tzs", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "tenant_wallets",
        sa.Column(
            "reserved_balance_tzs", sa.Numeric(14, 2), nullable=False, server_default="0"
        ),
    )
    op.add_column(
        "tenant_wallets",
        sa.Column("frozen_balance_tzs", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )
    op.add_column(
        "tenant_wallets",
        sa.Column(
            "total_disbursed_tzs", sa.Numeric(14, 2), nullable=False, server_default="0"
        ),
    )
    # Any pre-existing balance (dev/test data only) becomes available —
    # the honest, most-liquid bucket, rather than assumed settled/pending.
    op.execute("UPDATE tenant_wallets SET available_balance_tzs = balance")
    op.drop_column("tenant_wallets", "balance")

    # ------------------------------------------------------------- ledger_entries
    op.add_column(
        "ledger_entries",
        sa.Column("direction", sa.Text(), nullable=False, server_default="credit"),
    )
    op.add_column("ledger_entries", sa.Column("wallet_bucket", sa.Text(), nullable=True))
    op.add_column(
        "ledger_entries",
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Best-effort backfill of pre-existing rows (dev/test only — the old
    # generic credit/debit vocabulary predates this migration and every
    # such row so far was a captive-portal payment credit).
    op.execute(
        "UPDATE ledger_entries SET entry_type = 'TENANT_SHARE', wallet_bucket = 'available', "
        "direction = 'credit' WHERE entry_type = 'credit'"
    )
    op.execute(
        "UPDATE ledger_entries SET entry_type = 'ADJUSTMENT', wallet_bucket = 'available', "
        "direction = 'debit' WHERE entry_type = 'debit'"
    )

    op.create_check_constraint(
        "ck_ledger_entries_entry_type",
        "ledger_entries",
        "entry_type IN ('COLLECTION', 'TENANT_SHARE', 'PLATFORM_FEE', 'REFUND', 'REVERSAL', "
        "'DISBURSEMENT', 'DISBURSEMENT_REVERSAL', 'ADJUSTMENT')",
    )
    op.create_check_constraint(
        "ck_ledger_entries_direction", "ledger_entries", "direction IN ('credit', 'debit')"
    )
    op.create_check_constraint(
        "ck_ledger_entries_wallet_bucket",
        "ledger_entries",
        "wallet_bucket IS NULL OR wallet_bucket IN "
        "('available', 'pending', 'reserved', 'frozen', 'total_disbursed')",
    )

    # --------------------------------------------------------- commercial terms
    op.create_table(
        "tenant_commercial_terms",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("commission_rate_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "effective_from",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "commission_rate_percent >= 0 AND commission_rate_percent <= 100",
            name="ck_tenant_commercial_terms_rate_range",
        ),
    )
    op.create_index(
        "ix_tenant_commercial_terms_tenant_id", "tenant_commercial_terms", ["tenant_id"]
    )
    # Exactly one active commercial-terms row per tenant at a time — old
    # rows are deactivated (is_active=false), never edited or deleted.
    op.execute(
        "CREATE UNIQUE INDEX uq_tenant_commercial_terms_active "
        "ON tenant_commercial_terms (tenant_id) WHERE is_active"
    )


def downgrade() -> None:
    op.drop_index("uq_tenant_commercial_terms_active", table_name="tenant_commercial_terms")
    op.drop_index("ix_tenant_commercial_terms_tenant_id", table_name="tenant_commercial_terms")
    op.drop_table("tenant_commercial_terms")

    op.drop_constraint("ck_ledger_entries_wallet_bucket", "ledger_entries", type_="check")
    op.drop_constraint("ck_ledger_entries_direction", "ledger_entries", type_="check")
    op.drop_constraint("ck_ledger_entries_entry_type", "ledger_entries", type_="check")
    op.execute("UPDATE ledger_entries SET entry_type = 'credit' WHERE direction = 'credit'")
    op.execute("UPDATE ledger_entries SET entry_type = 'debit' WHERE direction = 'debit'")
    op.drop_column("ledger_entries", "actor_id")
    op.drop_column("ledger_entries", "wallet_bucket")
    op.drop_column("ledger_entries", "direction")

    op.add_column(
        "tenant_wallets",
        sa.Column("balance", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )
    op.execute("UPDATE tenant_wallets SET balance = available_balance_tzs + pending_balance_tzs")
    op.drop_column("tenant_wallets", "total_disbursed_tzs")
    op.drop_column("tenant_wallets", "frozen_balance_tzs")
    op.drop_column("tenant_wallets", "reserved_balance_tzs")
    op.drop_column("tenant_wallets", "pending_balance_tzs")
    op.drop_column("tenant_wallets", "available_balance_tzs")
