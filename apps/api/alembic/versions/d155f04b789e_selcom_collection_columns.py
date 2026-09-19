"""selcom collection columns on transactions

Revision ID: d155f04b789e
Revises: 9c1e5f4a2d7b
Create Date: 2026-09-19 15:00:00.000000

Adds the columns app/services/collections.py needs to drive a Selcom
Mobile Checkout Collection order (create-order-minimal -> wallet-payment
STK push -> webhook/order-status reconciliation) through the existing
`transactions` table — see app/models/finance.py.Transaction's updated
docstring. `reference` (already existed, unique per tenant) becomes our
own server-generated order_id; `provider_reference` (already existed)
becomes Selcom's own payment identifier. `status` keeps its existing
Text column but its default moves from the old free-text "pending" to
CollectionStatus.CREATED ("CREATED") — the table has never had real
production rows (this integration was never implemented until now), so
no data migration is needed for the value change itself.

New columns, all nullable (or a safe server_default), so this is a
purely additive, backward-compatible change:
- collection_transid: our own generated wallet-payment transid
- payer_phone: normalized 255XXXXXXXXX the STK was sent to
- provider_resultcode / provider_message: Selcom's own result fields
- stk_requested_at / completed_at / failed_at: lifecycle timestamps
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d155f04b789e"
down_revision: str | None = "9c1e5f4a2d7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("collection_transid", sa.Text(), nullable=True))
    op.add_column("transactions", sa.Column("payer_phone", sa.Text(), nullable=True))
    op.add_column("transactions", sa.Column("provider_resultcode", sa.Text(), nullable=True))
    op.add_column("transactions", sa.Column("provider_message", sa.Text(), nullable=True))
    op.add_column(
        "transactions",
        sa.Column("stk_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "transactions", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "transactions", sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.alter_column(
        "transactions", "status", server_default="CREATED", existing_type=sa.Text()
    )


def downgrade() -> None:
    op.alter_column(
        "transactions", "status", server_default="pending", existing_type=sa.Text()
    )
    op.drop_column("transactions", "failed_at")
    op.drop_column("transactions", "completed_at")
    op.drop_column("transactions", "stk_requested_at")
    op.drop_column("transactions", "provider_message")
    op.drop_column("transactions", "provider_resultcode")
    op.drop_column("transactions", "payer_phone")
    op.drop_column("transactions", "collection_transid")
