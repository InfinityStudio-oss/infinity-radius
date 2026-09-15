"""captive portal: tenant branding, optional customer names

Revision ID: f3513f545a5d
Revises: 5b30bbd257fc
Create Date: 2026-09-15 09:00:00.000000

- tenants: logo_url/brand_color (tenant-supplied; both null until a tenant
  sets their own — the captive portal falls back to the platform's own
  branding when unset, never a fabricated logo/color).
- customers: first_name/last_name become nullable — the captive portal's
  self-service payment flow only ever collects a phone number, so a
  customer created that way genuinely has no name yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3513f545a5d"
down_revision: str | None = "5b30bbd257fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("logo_url", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("brand_color", sa.Text(), nullable=True))

    op.alter_column("customers", "first_name", existing_type=sa.Text(), nullable=True)
    op.alter_column("customers", "last_name", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE customers SET first_name = 'Unknown' WHERE first_name IS NULL")
    op.execute("UPDATE customers SET last_name = 'Customer' WHERE last_name IS NULL")
    op.alter_column("customers", "last_name", existing_type=sa.Text(), nullable=False)
    op.alter_column("customers", "first_name", existing_type=sa.Text(), nullable=False)

    op.drop_column("tenants", "brand_color")
    op.drop_column("tenants", "logo_url")
