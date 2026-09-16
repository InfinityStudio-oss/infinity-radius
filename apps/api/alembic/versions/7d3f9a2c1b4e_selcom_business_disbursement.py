"""selcom business disbursement: threshold approval, destination codes

Revision ID: 7d3f9a2c1b4e
Revises: 11075bc476b4
Create Date: 2026-09-16 09:00:00.000000

- withdrawals: adds AMBIGUOUS to the status vocabulary (Selcom resultcode
  999 — never retried, resolved only by transaction/query reconciliation);
  approval_required (persisted at request time — an explicit, auditable
  fact independent of the threshold setting possibly changing later);
  verified_recipient_name (the Selcom account/lookup-confirmed name
  actually used for transfer — never a client-supplied override);
  provider_charge/provider_result_code/provider_message (Selcom's own
  transaction/process + transaction/query results, for reconciliation).
- withdrawal_destinations: adds destination_code — the specific Selcom FI
  code (see app.core.enums.DestinationCode) a destination pays out
  through; channel stays as the broader mobile_money/bank category.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "7d3f9a2c1b4e"
down_revision: str | None = "11075bc476b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DESTINATION_CODES = (
    "SELCOM",
    "AIRTELMONEY",
    "HALOPESA",
    "MIXXBYYAS",
    "TTCLPESA",
    "MPESA",
    "ABSA",
    "BANCABC",
    "ACB",
    "AMANA",
    "AZANIA",
    "BOA",
    "BOBTZ",
    "BOI",
    "BOT",
    "CANARA",
    "CITI",
    "CRDB",
    "DCB",
    "DTB",
    "ECOBANK",
    "EQUITY",
    "EXIM",
    "FINCA",
    "GTBANK",
    "HABIB",
    "IMBANK",
    "ICB",
    "KCB",
    "LETSHEGO",
    "MAENDELEO",
    "MKOMBOZI",
    "MUCOBA",
    "MWALIMU",
    "MWANGA",
    "NBC",
    "NCBA",
    "NMB",
    "PBZ",
    "STANBIC",
    "SCB",
    "TCB",
    "UCHUMI",
    "UBA",
)


def upgrade() -> None:
    # ------------------------------------------------------------- withdrawals
    op.drop_constraint("ck_withdrawals_status", "withdrawals", type_="check")
    op.create_check_constraint(
        "ck_withdrawals_status",
        "withdrawals",
        "status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'PROCESSING', 'AMBIGUOUS', "
        "'SUCCESS', 'FAILED', 'REJECTED', 'CANCELLED', 'REVERSED')",
    )

    op.add_column(
        "withdrawals",
        sa.Column("approval_required", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "withdrawals", sa.Column("verified_recipient_name", sa.Text(), nullable=True)
    )
    op.add_column(
        "withdrawals", sa.Column("provider_charge", sa.Numeric(14, 2), nullable=True)
    )
    op.add_column("withdrawals", sa.Column("provider_result_code", sa.Text(), nullable=True))
    op.add_column("withdrawals", sa.Column("provider_message", sa.Text(), nullable=True))

    # --------------------------------------------------------- destinations
    op.add_column(
        "withdrawal_destinations", sa.Column("destination_code", sa.Text(), nullable=True)
    )
    codes_sql = ", ".join(f"'{code}'" for code in _DESTINATION_CODES)
    op.create_check_constraint(
        "ck_withdrawal_destinations_destination_code",
        "withdrawal_destinations",
        f"destination_code IS NULL OR destination_code IN ({codes_sql})",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_withdrawal_destinations_destination_code",
        "withdrawal_destinations",
        type_="check",
    )
    op.drop_column("withdrawal_destinations", "destination_code")

    op.drop_column("withdrawals", "provider_message")
    op.drop_column("withdrawals", "provider_result_code")
    op.drop_column("withdrawals", "provider_charge")
    op.drop_column("withdrawals", "verified_recipient_name")
    op.drop_column("withdrawals", "approval_required")

    op.drop_constraint("ck_withdrawals_status", "withdrawals", type_="check")
    op.execute("UPDATE withdrawals SET status = 'FAILED' WHERE status = 'AMBIGUOUS'")
    op.create_check_constraint(
        "ck_withdrawals_status",
        "withdrawals",
        "status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'PROCESSING', 'SUCCESS', "
        "'FAILED', 'REJECTED', 'CANCELLED', 'REVERSED')",
    )
