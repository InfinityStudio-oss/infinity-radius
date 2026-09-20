"""transactions.transaction_type discriminator

Revision ID: a762b365749e
Revises: d155f04b789e
Create Date: 2026-09-20 09:10:00.000000

`transactions` is shared by two unrelated payment families and had no
authoritative way to tell them apart:

    Selcom Mobile Checkout Collection  (app/services/collections.py)
    Captive portal payments            (app/services/captive_portal.py)

Everything previously available was a side effect rather than a
classification — `channel` is NULL on a Collection until it COMPLETES
(Selcom documents data.channel as "Available on COMPLETED payments
only"), `payer_phone`/`collection_transid` are presence heuristics, and
reference prefixes/status casing are brittle. A tenant's Collections
list built on any of those would silently start including unrelated rows
the moment a third writer appeared.

This adds an explicit discriminator. Both writers set it directly from
this revision onward — no DB default is relied on, so a future writer
that forgets it leaves NULL (visible, reviewable) rather than being
silently misfiled as a Collection.

DELIBERATELY NOT DONE HERE:
  * no NOT NULL — the column stays nullable through the first production
    rollout so the backfill can be verified against real rows first
  * no CHECK constraint — this codebase has no existing pattern of
    value-constrained Text columns (see `status`, also plain Text), and
    adding one now would make future values a migration each
Both can be tightened in a later revision once production data is
confirmed.

BACKFILL SAFETY: the two rules below are historical one-time
classification over a closed dataset, not runtime logic. Verified
against full git history before writing:
  * Collection references have been `col-{uuid4().hex}` since the single
    commit that introduced the integration (86fbf11) and never changed
  * Captive portal has set channel='captive_portal' with a `CP-` prefixed
    reference since the initial commit (99756fb) and never changed
  * those are the only two writers to this table
  * the rules cannot overlap: a captive portal row's reference is
    `CP-<uppercase hex>`, which never matches `col-%`
Rows matching neither rule are left NULL on purpose — an unknown row is
surfaced for review, never guessed into a payment family.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a762b365749e"
down_revision: str | None = "d155f04b789e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Additive, nullable, no default: existing rows are untouched by the
    # ADD COLUMN itself and stay NULL until the targeted UPDATEs below.
    op.add_column("transactions", sa.Column("transaction_type", sa.Text(), nullable=True))

    # Captive portal first: the narrower, stronger signal (an explicitly
    # written column value, not an absence).
    op.execute(
        """
        UPDATE transactions
           SET transaction_type = 'CAPTIVE_PORTAL'
         WHERE transaction_type IS NULL
           AND channel = 'captive_portal'
        """
    )

    # Collection second, and only for rows the first rule did not claim —
    # `transaction_type IS NULL` makes the two mutually exclusive even if
    # a row somehow satisfied both, so no row can be reclassified.
    op.execute(
        """
        UPDATE transactions
           SET transaction_type = 'COLLECTION'
         WHERE transaction_type IS NULL
           AND reference LIKE 'col-%'
        """
    )


def downgrade() -> None:
    # Drops only the column this revision added. The backfilled values are
    # lost with it, which is acceptable: they are reconstructible from the
    # same historical rules, and nothing outside this column changed.
    op.drop_column("transactions", "transaction_type")
