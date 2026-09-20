"""unify captive-portal payment statuses onto CollectionStatus

Revision ID: b7e3d9c1a548
Revises: c4f81b2e9a37
Create Date: 2026-09-20 13:05:00.000000

`transactions.status` was written in two different vocabularies by two
different writers:

    Collection      uppercase CollectionStatus  (CREATED/STK_SENT/COMPLETED/...)
    Captive portal  lowercase                   (pending/completed/failed)

One column, two languages. Every consumer then had to know which family a
row belonged to before it could interpret its own status column, and at
least two already got it wrong: the tenant dashboard's "failed today"
count and its per-package revenue sum both compared against the lowercase
spellings, so they silently matched nothing and reported 0 for every
Collection row. That class of bug is why this unifies rather than adding
another conditional.

DATA-ONLY. No schema change, no column added or dropped, no constraint,
no index. Purely a rewrite of existing values, and only within
transaction_type='CAPTIVE_PORTAL'.

MAPPING, and why each is the honest choice:

    'pending'   -> 'CREATED'    The row exists locally and NOTHING was
                                ever sent to a payment provider — captive
                                initiation has never had one wired up
                                (see app/services/captive_portal.py). Both
                                are non-terminal, so nothing becomes
                                reconcilable or terminal that was not
                                before. CollectionStatus.PENDING would be
                                wrong: it specifically means "an
                                order-status query came back still
                                waiting", and no such query ever happened.
    'completed' -> 'COMPLETED'  Same meaning, same terminality.
    'failed'    -> 'FAILED'     Same meaning, same terminality.

COLLECTION ROWS ARE NOT TOUCHED. Every statement is scoped to
transaction_type='CAPTIVE_PORTAL' AND an exact lowercase source value, so
an uppercase Collection row cannot match any of them. The predicates are
mutually exclusive, so no row can be rewritten twice.

activation_status FOR ALREADY-COMPLETED ROWS:
  A captive row reached 'completed' only inside the old all-in-one
  mark_transaction_completed(), which activated the subscription and
  provisioned RADIUS in the SAME database transaction — so if the status
  committed, activation had necessarily succeeded too. ACTIVE is therefore
  an inference from that code path, not a guess about unknown data.
  `activated_at` is deliberately left NULL: the real activation time was
  never recorded, and inventing one would put a fabricated timestamp into
  a support-facing audit field. NULL honestly means "activated, time
  unknown".

SIDE EFFECT, as in a762b365749e and c4f81b2e9a37: `transactions` carries a
BEFORE UPDATE trigger (public.set_updated_at) that bumps `updated_at` on
every row these statements touch. Metadata only; no financial column,
timestamp-of-record or ledger entry is affected.

PRODUCTION IMPACT AT TIME OF WRITING: zero rows. Production holds 2
transactions, both transaction_type='COLLECTION'. This migration is
written to be correct for the captive rows that exist in development and
for any that could exist, not because production has any.

DOWNGRADE restores the exact lowercase values, and clears only the
activation_status this revision set, so it is a true inverse.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7e3d9c1a548"
down_revision: str | None = "c4f81b2e9a37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (lowercase legacy value, CollectionStatus value)
_STATUS_MAP: tuple[tuple[str, str], ...] = (
    ("pending", "CREATED"),
    ("completed", "COMPLETED"),
    ("failed", "FAILED"),
)


def upgrade() -> None:
    for legacy, unified in _STATUS_MAP:
        op.execute(
            f"""
            UPDATE transactions
               SET status = '{unified}'
             WHERE transaction_type = 'CAPTIVE_PORTAL'
               AND status = '{legacy}'
            """
        )

    # Rows that were already 'completed' had necessarily finished
    # activation too — see this revision's docstring. Scoped to rows with
    # no activation_status yet so a value set by the new code is never
    # overwritten.
    op.execute(
        """
        UPDATE transactions
           SET activation_status = 'ACTIVE'
         WHERE transaction_type = 'CAPTIVE_PORTAL'
           AND status = 'COMPLETED'
           AND activation_status IS NULL
        """
    )


def downgrade() -> None:
    # Clear first, while COMPLETED still identifies the affected rows.
    op.execute(
        """
        UPDATE transactions
           SET activation_status = NULL
         WHERE transaction_type = 'CAPTIVE_PORTAL'
           AND status = 'COMPLETED'
           AND activation_status = 'ACTIVE'
        """
    )
    for legacy, unified in _STATUS_MAP:
        op.execute(
            f"""
            UPDATE transactions
               SET status = '{legacy}'
             WHERE transaction_type = 'CAPTIVE_PORTAL'
               AND status = '{unified}'
            """
        )
