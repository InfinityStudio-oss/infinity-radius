"""rls policies

Revision ID: 41619a38de4a
Revises: fca46a843307
Create Date: 2026-09-12 21:55:05.161279

Row Level Security for every tenant-scoped table, plus the trusted
`public.current_tenant_id()` / `public.is_super_admin()` helpers and the
auth.users -> profiles provisioning trigger.

This migration assumes `auth.users` and `auth.uid()` already exist in the
target database, as they do on every real Supabase project (Supabase Auth
owns the `auth` schema). It does not create or modify anything in `auth`
beyond attaching a trigger to `auth.users`.

See docs/rls-policies.md for the full policy reference and the rationale
behind each table's access pattern.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "41619a38de4a"
down_revision: str | None = "fca46a843307"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tables where any tenant member (or super admin) may select/insert/update/delete
# their own tenant's rows — everyday operational CRUD.
FULL_CRUD_TABLES = [
    "locations",
    "routers",
    "packages",
    "customers",
    "customer_devices",
    "subscriptions",
    "voucher_batches",
    "offline_vouchers",
    "withdrawal_destinations",
]

# Tables where rows may be created/edited but never deleted by tenant
# clients — a financial trail is corrected with new rows, not erasure.
NO_DELETE_TABLES = ["transactions", "withdrawals"]

# Tables written only by the trusted backend (which connects with a role
# that bypasses RLS entirely) — tenant clients get read-only visibility.
SELECT_ONLY_TABLES = [
    "user_sessions",
    "payment_webhooks",
    "tenant_wallets",
    "ledger_entries",
    "settlement_logs",
    "audit_logs",
]

# Immutable system reference data — readable by anyone authenticated,
# writable by no one at request time (only by this migration).
REFERENCE_TABLES = ["roles", "permissions", "role_permissions"]

ALL_TENANT_TABLES = FULL_CRUD_TABLES + NO_DELETE_TABLES + SELECT_ONLY_TABLES


def upgrade() -> None:
    # --- Trusted tenant-context helpers ---------------------------------
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.current_tenant_id()
        RETURNS uuid
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
          SELECT tenant_id FROM public.profiles WHERE id = auth.uid()
        $$
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.is_super_admin()
        RETURNS boolean
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = public
        AS $$
          SELECT EXISTS (
            SELECT 1
            FROM public.profile_roles pr
            JOIN public.roles r ON r.id = pr.role_id
            WHERE pr.profile_id = auth.uid()
              AND r.code = 'SUPER_ADMIN'
          )
        $$
        """
    )

    # --- auth.users -> profiles provisioning (invitation-ready) ---------
    # Fires on self-signup AND on supabase.auth.admin.inviteUserByEmail —
    # both insert into auth.users. tenant_id/roles are assigned afterwards
    # by a tenant admin or super admin, not by this trigger.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION public.handle_new_auth_user()
        RETURNS trigger
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = public
        AS $$
        BEGIN
          INSERT INTO public.profiles (id, email, full_name, status)
          VALUES (
            NEW.id,
            NEW.email,
            NEW.raw_user_meta_data ->> 'full_name',
            'invited'
          )
          ON CONFLICT (id) DO NOTHING;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER on_auth_user_created
        AFTER INSERT ON auth.users
        FOR EACH ROW
        EXECUTE FUNCTION public.handle_new_auth_user()
        """
    )

    # --- Reference tables: read-only for everyone, immutable in place ---
    for table_name in REFERENCE_TABLES:
        op.execute(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table_name}_select_all ON public.{table_name}
            FOR SELECT
            TO authenticated
            USING (true)
            """
        )

    # --- tenants ----------------------------------------------------------
    op.execute("ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY tenants_select ON public.tenants
        FOR SELECT TO authenticated
        USING (id = public.current_tenant_id() OR public.is_super_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY tenants_insert ON public.tenants
        FOR INSERT TO authenticated
        WITH CHECK (public.is_super_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY tenants_update ON public.tenants
        FOR UPDATE TO authenticated
        USING (id = public.current_tenant_id() OR public.is_super_admin())
        WITH CHECK (id = public.current_tenant_id() OR public.is_super_admin())
        """
    )
    op.execute(
        """
        CREATE POLICY tenants_delete ON public.tenants
        FOR DELETE TO authenticated
        USING (public.is_super_admin())
        """
    )

    # --- profiles -----------------------------------------------------
    op.execute("ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY profiles_select ON public.profiles
        FOR SELECT TO authenticated
        USING (
          id = auth.uid()
          OR tenant_id = public.current_tenant_id()
          OR public.is_super_admin()
        )
        """
    )
    # No INSERT policy: profiles are only ever created by the
    # handle_new_auth_user trigger (SECURITY DEFINER, bypasses RLS).
    op.execute(
        """
        CREATE POLICY profiles_update ON public.profiles
        FOR UPDATE TO authenticated
        USING (
          id = auth.uid()
          OR tenant_id = public.current_tenant_id()
          OR public.is_super_admin()
        )
        WITH CHECK (
          id = auth.uid()
          OR tenant_id = public.current_tenant_id()
          OR public.is_super_admin()
        )
        """
    )

    # --- profile_roles ---------------------------------------------------
    op.execute("ALTER TABLE public.profile_roles ENABLE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY profile_roles_select ON public.profile_roles
        FOR SELECT TO authenticated
        USING (
          profile_id = auth.uid()
          OR tenant_id = public.current_tenant_id()
          OR public.is_super_admin()
        )
        """
    )
    for action, clause in (("INSERT", "WITH CHECK"), ("UPDATE", "USING"), ("DELETE", "USING")):
        op.execute(
            f"""
            CREATE POLICY profile_roles_{action.lower()} ON public.profile_roles
            FOR {action} TO authenticated
            {clause} (tenant_id = public.current_tenant_id() OR public.is_super_admin())
            """
        )

    # --- Standard full-CRUD tenant tables --------------------------------
    for table_name in FULL_CRUD_TABLES:
        op.execute(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table_name}_select ON public.{table_name}
            FOR SELECT TO authenticated
            USING (tenant_id = public.current_tenant_id() OR public.is_super_admin())
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table_name}_insert ON public.{table_name}
            FOR INSERT TO authenticated
            WITH CHECK (tenant_id = public.current_tenant_id() OR public.is_super_admin())
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table_name}_update ON public.{table_name}
            FOR UPDATE TO authenticated
            USING (tenant_id = public.current_tenant_id() OR public.is_super_admin())
            WITH CHECK (tenant_id = public.current_tenant_id() OR public.is_super_admin())
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table_name}_delete ON public.{table_name}
            FOR DELETE TO authenticated
            USING (tenant_id = public.current_tenant_id() OR public.is_super_admin())
            """
        )

    # --- No-delete tenant tables (financial trail) -----------------------
    for table_name in NO_DELETE_TABLES:
        op.execute(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table_name}_select ON public.{table_name}
            FOR SELECT TO authenticated
            USING (tenant_id = public.current_tenant_id() OR public.is_super_admin())
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table_name}_insert ON public.{table_name}
            FOR INSERT TO authenticated
            WITH CHECK (tenant_id = public.current_tenant_id() OR public.is_super_admin())
            """
        )
        op.execute(
            f"""
            CREATE POLICY {table_name}_update ON public.{table_name}
            FOR UPDATE TO authenticated
            USING (tenant_id = public.current_tenant_id() OR public.is_super_admin())
            WITH CHECK (tenant_id = public.current_tenant_id() OR public.is_super_admin())
            """
        )

    # --- Backend-only-write tenant tables (read-only to clients) --------
    for table_name in SELECT_ONLY_TABLES:
        op.execute(f"ALTER TABLE public.{table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {table_name}_select ON public.{table_name}
            FOR SELECT TO authenticated
            USING (tenant_id = public.current_tenant_id() OR public.is_super_admin())
            """
        )


def downgrade() -> None:
    for table_name in REFERENCE_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table_name}_select_all ON public.{table_name}")
        op.execute(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY")

    for table_name in ["tenants", "profiles", "profile_roles", *ALL_TENANT_TABLES]:
        op.execute(f"DROP POLICY IF EXISTS {table_name}_select ON public.{table_name}")
        op.execute(f"DROP POLICY IF EXISTS {table_name}_insert ON public.{table_name}")
        op.execute(f"DROP POLICY IF EXISTS {table_name}_update ON public.{table_name}")
        op.execute(f"DROP POLICY IF EXISTS {table_name}_delete ON public.{table_name}")
        op.execute(f"ALTER TABLE public.{table_name} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users")
    op.execute("DROP FUNCTION IF EXISTS public.handle_new_auth_user()")
    op.execute("DROP FUNCTION IF EXISTS public.is_super_admin()")
    op.execute("DROP FUNCTION IF EXISTS public.current_tenant_id()")
