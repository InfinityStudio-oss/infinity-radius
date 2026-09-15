"""selcom disbursement architecture: maker-checker withdrawals, settlement mode

Revision ID: 594adc71a075
Revises: 02afe6ac6800
Create Date: 2026-09-13 12:00:00.000000

- tenant_settlement_config: a new table. Per-tenant, versioned, exactly one
  active row — which architecture mode applies (direct_merchant_settlement,
  the safe default meaning Infinity Radius does not hold this tenant's
  funds, vs platform_managed_wallet). See app.core.enums.SettlementMode /
  app/services/settlement_config.py.
- withdrawals: full maker-checker lifecycle columns (idempotency_key,
  provider_reference, failure_reason, submitted_at, completed_at,
  reviewed_by/reviewed_at/review_notes replacing approved_by, and hashed
  2FA challenge columns), plus a CHECK constraint on the 9-state status
  vocabulary (app.core.enums.WithdrawalStatus).
- withdrawal_events: a new table — the immutable status-transition log for
  one withdrawal, distinct from ledger_entries (money movement only).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "594adc71a075"
down_revision: str | None = "02afe6ac6800"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --------------------------------------------------------- settlement mode
    op.create_table(
        "tenant_settlement_config",
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
        sa.Column("mode", sa.Text(), nullable=False),
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
            "mode IN ('direct_merchant_settlement', 'platform_managed_wallet')",
            name="ck_tenant_settlement_config_mode",
        ),
    )
    op.create_index(
        "ix_tenant_settlement_config_tenant_id", "tenant_settlement_config", ["tenant_id"]
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_tenant_settlement_config_active "
        "ON tenant_settlement_config (tenant_id) WHERE is_active"
    )

    # ------------------------------------------------------------- withdrawals
    op.add_column(
        "withdrawals",
        sa.Column(
            "idempotency_key",
            sa.Text(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()::text"),
        ),
    )
    op.create_unique_constraint(
        "uq_withdrawals_idempotency_key", "withdrawals", ["idempotency_key"]
    )
    op.add_column("withdrawals", sa.Column("provider_reference", sa.Text(), nullable=True))
    op.add_column("withdrawals", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.add_column(
        "withdrawals", sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "withdrawals", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )

    op.add_column(
        "withdrawals",
        sa.Column(
            "reviewed_by",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.execute("UPDATE withdrawals SET reviewed_by = approved_by")
    op.drop_column("withdrawals", "approved_by")
    op.add_column(
        "withdrawals", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("withdrawals", sa.Column("review_notes", sa.Text(), nullable=True))

    op.add_column("withdrawals", sa.Column("two_factor_code_hash", sa.Text(), nullable=True))
    op.add_column(
        "withdrawals",
        sa.Column("two_factor_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "withdrawals",
        sa.Column("two_factor_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "withdrawals",
        sa.Column("two_factor_confirmed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Best-effort backfill of the old 4-state vocabulary (dev/test only —
    # no withdrawal has ever actually reached Selcom) onto the new 9-state
    # one before the CHECK constraint goes on.
    op.execute("UPDATE withdrawals SET status = 'PENDING_APPROVAL' WHERE status = 'pending'")
    op.execute("UPDATE withdrawals SET status = 'PROCESSING' WHERE status = 'processing'")
    op.execute("UPDATE withdrawals SET status = 'SUCCESS' WHERE status = 'completed'")
    op.execute("UPDATE withdrawals SET status = 'FAILED' WHERE status = 'failed'")
    op.alter_column("withdrawals", "status", server_default="DRAFT")
    op.create_check_constraint(
        "ck_withdrawals_status",
        "withdrawals",
        "status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'PROCESSING', 'SUCCESS', "
        "'FAILED', 'REJECTED', 'CANCELLED', 'REVERSED')",
    )

    # --------------------------------------------------------- withdrawal_events
    op.create_table(
        "withdrawal_events",
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
        sa.Column(
            "withdrawal_id",
            UUID(as_uuid=True),
            sa.ForeignKey("withdrawals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.Text(), nullable=True),
        sa.Column("to_status", sa.Text(), nullable=False),
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_withdrawal_events_withdrawal_id", "withdrawal_events", ["withdrawal_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_withdrawal_events_withdrawal_id", table_name="withdrawal_events")
    op.drop_table("withdrawal_events")

    op.drop_constraint("ck_withdrawals_status", "withdrawals", type_="check")
    op.execute("UPDATE withdrawals SET status = 'pending' WHERE status = 'PENDING_APPROVAL'")
    op.execute("UPDATE withdrawals SET status = 'processing' WHERE status = 'PROCESSING'")
    op.execute("UPDATE withdrawals SET status = 'completed' WHERE status = 'SUCCESS'")
    op.execute("UPDATE withdrawals SET status = 'failed' WHERE status = 'FAILED'")
    op.execute(
        "UPDATE withdrawals SET status = 'pending' WHERE status IN "
        "('DRAFT', 'APPROVED', 'REJECTED', 'CANCELLED', 'REVERSED')"
    )
    op.alter_column("withdrawals", "status", server_default="pending")

    op.drop_column("withdrawals", "two_factor_confirmed_at")
    op.drop_column("withdrawals", "two_factor_attempts")
    op.drop_column("withdrawals", "two_factor_expires_at")
    op.drop_column("withdrawals", "two_factor_code_hash")

    op.drop_column("withdrawals", "review_notes")
    op.drop_column("withdrawals", "reviewed_at")
    op.add_column(
        "withdrawals",
        sa.Column(
            "approved_by",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.execute("UPDATE withdrawals SET approved_by = reviewed_by")
    op.drop_column("withdrawals", "reviewed_by")

    op.drop_column("withdrawals", "completed_at")
    op.drop_column("withdrawals", "submitted_at")
    op.drop_column("withdrawals", "failure_reason")
    op.drop_column("withdrawals", "provider_reference")
    op.drop_constraint("uq_withdrawals_idempotency_key", "withdrawals", type_="unique")
    op.drop_column("withdrawals", "idempotency_key")

    op.drop_index("uq_tenant_settlement_config_active", table_name="tenant_settlement_config")
    op.drop_index(
        "ix_tenant_settlement_config_tenant_id", table_name="tenant_settlement_config"
    )
    op.drop_table("tenant_settlement_config")
