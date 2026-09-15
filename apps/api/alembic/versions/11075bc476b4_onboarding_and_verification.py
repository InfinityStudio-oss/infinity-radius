"""onboarding and verification

Revision ID: 11075bc476b4
Revises: 594adc71a075
Create Date: 2026-09-14 09:00:00.000000

Adds the real client signup + business onboarding + Super Admin approval
workflow: business/owner detail columns on `tenants`, `first_name`/
`last_name` on `profiles`, and four new tables — `tenant_settings`,
`tenant_feature_flags`, `tenant_verifications`, `email_events`.

`tenants.status` moves from a free-text "active" default to a real
workflow (PENDING_VERIFICATION | ACTIVE | MORE_INFORMATION_REQUIRED |
REJECTED | SUSPENDED) — existing "active" rows are normalized to "ACTIVE"
so nothing already-approved silently reverts to pending.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "11075bc476b4"
down_revision: str | None = "594adc71a075"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# tenant_settings, tenant_feature_flags, tenant_verifications: readable by
# tenant members + super admin, writable only by the trusted backend
# (SECURITY DEFINER / service-role bypasses RLS) — same pattern as
# tenant_wallets/ledger_entries in the rls_policies migration.
READ_ONLY_TENANT_TABLES = ["tenant_settings", "tenant_feature_flags", "tenant_verifications"]


def upgrade() -> None:
    # --- tenants: business/owner/location detail + real status workflow ---
    op.add_column("tenants", sa.Column("legal_name", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("business_type", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("business_email", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("business_phone", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("tin", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("business_license_number", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("region", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("district", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("ward", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("street_area", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("address", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("authorized_contact_name", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("authorized_contact_position", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("authorized_contact_phone", sa.Text(), nullable=True))
    op.add_column("tenants", sa.Column("authorized_contact_email", sa.Text(), nullable=True))
    op.add_column(
        "tenants", sa.Column("accepted_terms_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "tenants", sa.Column("accepted_privacy_at", sa.DateTime(timezone=True), nullable=True)
    )

    # Normalize existing rows before changing the default for new ones —
    # nothing already-active should read as newly pending.
    op.execute("UPDATE public.tenants SET status = 'ACTIVE' WHERE status = 'active'")
    op.alter_column(
        "tenants", "status", server_default="PENDING_VERIFICATION", existing_type=sa.Text()
    )

    # --- profiles: split name, matching the onboarding form's Account Owner section ---
    op.add_column("profiles", sa.Column("first_name", sa.Text(), nullable=True))
    op.add_column("profiles", sa.Column("last_name", sa.Text(), nullable=True))

    # --- tenant_settings: minimal, extensible per-tenant preferences row ---
    op.create_table(
        "tenant_settings",
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
            unique=True,
        ),
        sa.Column("preferences", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # --- tenant_feature_flags: gates that must be explicitly turned on, never
    # implied by "the tenant exists" — see app/services/onboarding.py and
    # app/services/admin_tenants.py for the only writers. ---
    op.create_table(
        "tenant_feature_flags",
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
            unique=True,
        ),
        sa.Column("collection_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("payout_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("api_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # --- tenant_verifications: the Super Admin review record — one row per
    # tenant, mirroring (and the authoritative source for) tenants.status. ---
    op.create_table(
        "tenant_verifications",
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
            unique=True,
        ),
        sa.Column(
            "status", sa.Text(), nullable=False, server_default="PENDING_VERIFICATION"
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "reviewed_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("more_information_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # --- email_events: every Resend send attempt, tenant onboarding and
    # beyond — mirrors payment_webhooks' nullable tenant_id (a send can
    # precede/fail independent of tenant resolution in edge cases). ---
    op.create_table(
        "email_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("recipient", sa.Text(), nullable=False),
        sa.Column("email_type", sa.Text(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False, server_default="RESEND"),
        sa.Column("provider_message_id", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="SENT"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_email_events_tenant_id", "email_events", ["tenant_id"])

    # --- updated_at triggers for the three new timestamped tables ---
    for table_name in ["tenant_settings", "tenant_feature_flags", "tenant_verifications"]:
        op.execute(
            f"""
            CREATE TRIGGER set_updated_at
            BEFORE UPDATE ON public.{table_name}
            FOR EACH ROW
            EXECUTE FUNCTION public.set_updated_at()
            """
        )

    # --- RLS: read-only tenant tables (backend-only writes) --------------
    for table_name in READ_ONLY_TENANT_TABLES:
        op.execute(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table_name}_select ON public.{table_name}
            FOR SELECT TO authenticated
            USING (tenant_id = public.current_tenant_id() OR public.is_super_admin())
            """
        )

    # --- RLS: email_events, same read-only pattern ------------------------
    op.execute("ALTER TABLE public.email_events ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY email_events_select ON public.email_events
        FOR SELECT TO authenticated
        USING (tenant_id = public.current_tenant_id() OR public.is_super_admin())
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS email_events_select ON public.email_events")
    op.execute("ALTER TABLE public.email_events DISABLE ROW LEVEL SECURITY")
    for table_name in READ_ONLY_TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table_name}_select ON public.{table_name}")
        op.execute(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY")

    for table_name in ["tenant_settings", "tenant_feature_flags", "tenant_verifications"]:
        op.execute(f"DROP TRIGGER IF EXISTS set_updated_at ON public.{table_name}")

    op.drop_index("ix_email_events_tenant_id", table_name="email_events")
    op.drop_table("email_events")
    op.drop_table("tenant_verifications")
    op.drop_table("tenant_feature_flags")
    op.drop_table("tenant_settings")

    op.drop_column("profiles", "last_name")
    op.drop_column("profiles", "first_name")

    op.alter_column("tenants", "status", server_default="active", existing_type=sa.Text())
    for column_name in [
        "accepted_privacy_at",
        "accepted_terms_at",
        "address",
        "street_area",
        "ward",
        "district",
        "region",
        "authorized_contact_email",
        "authorized_contact_phone",
        "authorized_contact_position",
        "authorized_contact_name",
        "business_license_number",
        "tin",
        "business_phone",
        "business_email",
        "business_type",
        "legal_name",
    ]:
        op.drop_column("tenants", column_name)
