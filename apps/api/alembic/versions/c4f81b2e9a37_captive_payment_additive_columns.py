"""captive portal payment + fulfillment columns, and captive_sessions

Revision ID: c4f81b2e9a37
Revises: a762b365749e
Create Date: 2026-09-20 12:05:00.000000

Groundwork ONLY for wiring captive-portal package payments to the
validated Selcom Mobile Checkout provider (app/services/
selcom_payment_provider.py, extracted in e33fb70). Nothing in this
revision changes any existing behavior: every column added to
`transactions` is nullable with no default, so existing rows are
untouched and every current writer keeps working unchanged.

WHY EACH COLUMN EXISTS
  payment_provider    `transaction_type` says which BUSINESS FLOW a row
                      belongs to (COLLECTION vs CAPTIVE_PORTAL); it does
                      NOT say which provider processed it. Reconciliation
                      needs the second question answered independently,
                      because a captive-portal payment paid through Selcom
                      must be swept exactly like a tenant Collection,
                      while a future voucher/cash captive payment must
                      never be sent to Selcom's order-status at all.
  package_id          Which package was bought. Today this is only
                      reachable via subscription.package_id, which is
                      useless for a payment that never completed.
  router_id           Which site the payment came from — the first thing
                      support needs and currently unrecoverable.
  device_mac          Accepted by the captive portal API today but written
                      only into audit metadata, never a queryable column.
  captive_session_id  Links an attempt to the session that authorized it.
  activation_status   PAYMENT VERIFIED and ACCESS ACTIVATED are different
                      facts. Overloading `status` with both would make
                      "paid but activation failed" indistinguishable from
                      "not paid" — the one state that must never be
                      confused, since the customer has already been
                      charged.
  activated_at        When access actually started.

DELIBERATELY NOT DONE HERE
  * no NOT NULL and no server_default on ANY `transactions` column — the
    table holds live production rows, so both would be a rewrite/blocking
    change. Every writer sets these explicitly or leaves them NULL.
  * no CHECK constraints — consistent with `status`/`transaction_type`,
    which are plain Text (see a762b365749e for the same reasoning).
  * NO status-vocabulary change. `transactions.status` still holds
    uppercase CollectionStatus for Collection rows and lowercase
    'pending'/'completed'/'failed' for captive-portal rows. Unifying them
    rewrites live values and belongs in its own reviewed revision.
  * no backfill of CAPTIVE_PORTAL rows' payment_provider. No captive
    payment has ever reached a provider (its initiation path contacted
    nobody — see app/services/captive_portal.py), so the honest value is
    NULL. Guessing 'SELCOM_COLLECTION' there would fabricate history and,
    worse, make reconciliation query Selcom for orders that never existed.

BACKFILL SAFETY
  One statement, one value, one narrowly-scoped predicate:
      payment_provider = 'SELCOM_COLLECTION' WHERE transaction_type = 'COLLECTION'
  Every COLLECTION row was created by CollectionService, which has only
  ever talked to Selcom Mobile Checkout — verified across the full git
  history of that service. The predicate reads the authoritative
  discriminator, not a reference prefix or other heuristic.

KNOWN, ACCEPTED SIDE EFFECT
  `transactions` carries a BEFORE UPDATE trigger (public.set_updated_at,
  from 78bb02eec08a) that unconditionally sets NEW.updated_at = now().
  The backfill UPDATE therefore bumps `updated_at` on every COLLECTION
  row it touches. This is metadata only — no financial column, status,
  timestamp-of-record (created_at/completed_at/failed_at) or ledger entry
  is affected. The same thing happened in a762b365749e and was reviewed
  and accepted then. It is NOT worked around here: suppressing it would
  need ALTER TABLE ... DISABLE TRIGGER, which takes an ACCESS EXCLUSIVE
  lock and requires table ownership — strictly more risk than the
  cosmetic bump it would avoid.

CAPTIVE_SESSIONS
  A brand-new, empty table, so NOT NULL on its integrity-critical columns
  costs nothing and is checked against zero existing rows. `expires_at`
  and `nonce` in particular MUST be NOT NULL: a session row with a NULL
  expiry is a credential that never expires, and a NULL nonce defeats the
  single-use replay protection the table exists to provide. This is the
  one place this revision uses NOT NULL, and only because the table is
  new and empty.

  Written only by the backend (the captive portal is unauthenticated and
  has no Supabase session), read by tenant staff for support — so it gets
  the same read-only RLS shape as tenant_settings/email_events: SELECT
  for `authenticated`, scoped to the caller's tenant or super admin, and
  no INSERT/UPDATE/DELETE policy at all.

  Nothing reads or writes this table yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c4f81b2e9a37"
down_revision: str | None = "a762b365749e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- captive_sessions: created FIRST, because transactions.captive_session_id
    # --- references it.
    op.create_table(
        "captive_sessions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "router_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("routers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The client MAC the hotspot redirect carried, when it carried one —
        # genuinely optional (local/dev testing without a real router has none).
        sa.Column("mac_address", sa.Text(), nullable=True),
        # Single-use replay control: the value embedded in the issued session
        # token. UNIQUE so a replayed token cannot create a second session.
        sa.Column("nonce", sa.Text(), nullable=False),
        # Set once the session's token is spent. NULL = not yet used.
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_captive_sessions_tenant_id", "captive_sessions", ["tenant_id"])
    op.create_index("ix_captive_sessions_router_id", "captive_sessions", ["router_id"])
    op.create_unique_constraint("uq_captive_sessions_nonce", "captive_sessions", ["nonce"])
    # Supports the expiry sweep that will delete/ignore stale sessions.
    op.create_index("ix_captive_sessions_expires_at", "captive_sessions", ["expires_at"])

    # --- transactions: seven additive, nullable, default-less columns ---
    op.add_column("transactions", sa.Column("payment_provider", sa.Text(), nullable=True))
    op.add_column(
        "transactions",
        sa.Column(
            "package_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("packages.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "transactions",
        sa.Column(
            "router_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("routers.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("transactions", sa.Column("device_mac", sa.Text(), nullable=True))
    op.add_column(
        "transactions",
        sa.Column(
            "captive_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("captive_sessions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("transactions", sa.Column("activation_status", sa.Text(), nullable=True))
    op.add_column(
        "transactions", sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Reconciliation's future discovery query: "every non-terminal payment
    # this provider owns", deliberately NOT scoped by transaction_type.
    op.create_index(
        "ix_transactions_payment_provider_status",
        "transactions",
        ["payment_provider", "status"],
    )
    op.create_index("ix_transactions_package_id", "transactions", ["package_id"])
    op.create_index("ix_transactions_router_id", "transactions", ["router_id"])
    op.create_index("ix_transactions_captive_session_id", "transactions", ["captive_session_id"])
    # Partial: only rows that have entered the fulfillment lifecycle matter,
    # and today that is none of them — so this index stays empty until the
    # captive flow lands, rather than indexing NULL for every existing row.
    op.create_index(
        "ix_transactions_activation_status",
        "transactions",
        ["activation_status"],
        postgresql_where=sa.text("activation_status IS NOT NULL"),
    )

    # --- backfill: the ONLY data change in this revision ---
    op.execute(
        """
        UPDATE transactions
           SET payment_provider = 'SELCOM_COLLECTION'
         WHERE transaction_type = 'COLLECTION'
           AND payment_provider IS NULL
        """
    )

    # --- RLS: read-only tenant visibility, backend-only writes ---
    op.execute("ALTER TABLE public.captive_sessions ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY captive_sessions_select ON public.captive_sessions
        FOR SELECT TO authenticated
        USING (tenant_id = public.current_tenant_id() OR public.is_super_admin())
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS captive_sessions_select ON public.captive_sessions")
    op.execute("ALTER TABLE public.captive_sessions DISABLE ROW LEVEL SECURITY")

    op.drop_index("ix_transactions_activation_status", table_name="transactions")
    op.drop_index("ix_transactions_captive_session_id", table_name="transactions")
    op.drop_index("ix_transactions_router_id", table_name="transactions")
    op.drop_index("ix_transactions_package_id", table_name="transactions")
    op.drop_index("ix_transactions_payment_provider_status", table_name="transactions")

    # Drops only what this revision added. The backfilled payment_provider
    # values go with the column, which is acceptable: they are exactly
    # reconstructible from transaction_type by re-running upgrade().
    op.drop_column("transactions", "activated_at")
    op.drop_column("transactions", "activation_status")
    op.drop_column("transactions", "captive_session_id")
    op.drop_column("transactions", "device_mac")
    op.drop_column("transactions", "router_id")
    op.drop_column("transactions", "package_id")
    op.drop_column("transactions", "payment_provider")

    op.drop_index("ix_captive_sessions_expires_at", table_name="captive_sessions")
    op.drop_constraint("uq_captive_sessions_nonce", "captive_sessions", type_="unique")
    op.drop_index("ix_captive_sessions_router_id", table_name="captive_sessions")
    op.drop_index("ix_captive_sessions_tenant_id", table_name="captive_sessions")
    op.drop_table("captive_sessions")
