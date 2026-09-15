"""transactions: add provider_reference

Revision ID: 52e3073aaba9
Revises: f3513f545a5d
Create Date: 2026-09-16 09:00:00.000000

Selcom's own Collection order identifier for a transaction, once a real
order-creation call returns one (see
app/integrations/selcom/collection.py's initiate_collection). Nullable —
unset whenever Selcom's API isn't configured/implemented, which is the
honest state of every environment today.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "52e3073aaba9"
down_revision: str | None = "f3513f545a5d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("transactions", sa.Column("provider_reference", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("transactions", "provider_reference")
