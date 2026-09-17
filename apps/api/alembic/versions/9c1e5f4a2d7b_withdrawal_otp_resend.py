"""withdrawal OTP resend bookkeeping

Revision ID: 9c1e5f4a2d7b
Revises: 7d3f9a2c1b4e
Create Date: 2026-09-18 09:00:00.000000

Adds resend-cooldown/cap and identity-binding bookkeeping for the
withdrawal OTP flow (app/services/two_factor.py, app/services/payouts.py):
otp_last_sent_at/otp_send_count back the resend cooldown and per-withdrawal
send cap, otp_sent_to_email lets verification detect (and refuse) a case
where the account's email changed after the OTP was issued. The existing
two_factor_code_hash/two_factor_expires_at/two_factor_attempts/
two_factor_confirmed_at columns are reused as-is for the OTP hash/expiry/
attempt-count/verified-at fields — no rename, no new table.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9c1e5f4a2d7b"
down_revision: str | None = "7d3f9a2c1b4e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "withdrawals", sa.Column("otp_last_sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "withdrawals",
        sa.Column("otp_send_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("withdrawals", sa.Column("otp_sent_to_email", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("withdrawals", "otp_sent_to_email")
    op.drop_column("withdrawals", "otp_send_count")
    op.drop_column("withdrawals", "otp_last_sent_at")
