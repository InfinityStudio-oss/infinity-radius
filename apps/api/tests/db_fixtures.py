"""Seeds and tears down real rows for integration tests against the local
Postgres (see tests/fixtures/supabase_auth_stub.sql + `alembic upgrade
head`). Every row created here is explicitly deleted at teardown — this
suite leaves the database exactly as empty as it found it, in keeping with
the platform's "no fake operational data" rule extending even to tests.

Uses a plain synchronous psycopg connection rather than the app's async
SQLAlchemy engine: FastAPI's TestClient drives requests through its own
event-loop portal, and a second asyncpg engine touched from a *different*
loop (e.g. an async test fixture) corrupts that connection pool on
Windows. Keeping fixture setup/teardown fully synchronous sidesteps it —
tests stay plain `def test_...`, matching the rest of the suite.
"""

from dataclasses import dataclass, field
from urllib.parse import urlparse
from uuid import UUID, uuid4

import psycopg

from app.core.config import get_settings


def _sync_dsn() -> str:
    """The same DATABASE_URL, translated from the app's asyncpg URL to a
    plain psycopg (v3) connection string."""
    url = str(get_settings().database_url)
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    return (
        f"host={parsed.hostname} port={parsed.port or 5432} "
        f"dbname={parsed.path.lstrip('/')} user={parsed.username} "
        f"password={parsed.password}"
    )


def _connect() -> psycopg.Connection:
    conn = psycopg.connect(_sync_dsn())
    conn.autocommit = True
    return conn


def seed_user(
    conn: psycopg.Connection,
    *,
    role_code: str | None = None,
    tenant_id: UUID | None = None,
    email: str | None = None,
) -> UUID:
    """Creates an auth.users row (firing the handle_new_auth_user trigger,
    which creates the matching profiles row), assigns it to `tenant_id`
    (None for a platform-wide role like SUPER_ADMIN), and grants it
    `role_code`. Returns the new user's id.

    `role_code=None` leaves the profile with no role at all — the exact
    state a just-registered account is in before any role is granted
    (e.g. before scripts.assign_super_admin ever runs against it).
    """
    user_id = uuid4()
    email = email or f"{user_id}@example.test"

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO auth.users (id, email) VALUES (%s, %s)", (user_id, email)
        )
        cur.execute(
            "UPDATE public.profiles SET tenant_id = %s, status = 'active' WHERE id = %s",
            (tenant_id, user_id),
        )
        if role_code is not None:
            cur.execute(
                """
                INSERT INTO public.profile_roles (profile_id, role_id, tenant_id)
                SELECT %s, r.id, %s FROM public.roles r WHERE r.code = %s
                """,
                (user_id, tenant_id, role_code),
            )
    return user_id


def seed_tenant(
    conn: psycopg.Connection, *, name: str = "Test Tenant", status: str = "ACTIVE"
) -> UUID:
    """Defaults to ACTIVE — most of the suite exercises ACTIVE-tenant
    behavior, not the onboarding/approval workflow itself (see
    test_onboarding.py and test_admin_tenants.py for that), and
    tenants.status now defaults to PENDING_VERIFICATION for real signups."""
    tenant_id = uuid4()
    slug = f"test-tenant-{tenant_id}"
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO public.tenants (id, name, slug, status) VALUES (%s, %s, %s, %s)",
            (tenant_id, name, slug, status),
        )
    return tenant_id


def delete_user(conn: psycopg.Connection, user_id: UUID) -> None:
    # Cascades to profiles / profile_roles via ON DELETE CASCADE.
    with conn.cursor() as cur:
        cur.execute("DELETE FROM auth.users WHERE id = %s", (user_id,))


def delete_tenant(conn: psycopg.Connection, tenant_id: UUID) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM public.tenants WHERE id = %s", (tenant_id,))


@dataclass
class SeededContext:
    """Context manager seeding a tenant + one user per role, cleaning up
    everything it created on exit — even if the test body raises."""

    tenant_id: UUID | None = None
    _user_ids: list[UUID] = field(default_factory=list)
    _conn: psycopg.Connection | None = None

    def __enter__(self) -> "SeededContext":
        self._conn = _connect()
        return self

    def new_tenant(self, name: str = "Test Tenant", status: str = "ACTIVE") -> UUID:
        assert self._conn is not None
        self.tenant_id = seed_tenant(self._conn, name=name, status=status)
        return self.tenant_id

    def new_user(
        self,
        *,
        role_code: str | None = None,
        tenant_id: UUID | None = None,
        email: str | None = None,
    ) -> UUID:
        assert self._conn is not None
        user_id = seed_user(self._conn, role_code=role_code, tenant_id=tenant_id, email=email)
        self._user_ids.append(user_id)
        return user_id

    def new_commercial_terms(
        self, *, tenant_id: UUID, commission_rate_percent: str = "10.00"
    ) -> UUID:
        """Every test that drives a real collection through WalletService
        must set this up first — process_collection fails closed
        (DomainValidationError) with no active commercial terms configured.
        Cascade-deleted with the tenant at teardown; no separate cleanup."""
        assert self._conn is not None
        terms_id = uuid4()
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.tenant_commercial_terms "
                "(id, tenant_id, commission_rate_percent, is_active) "
                "VALUES (%s, %s, %s, true)",
                (terms_id, tenant_id, commission_rate_percent),
            )
        return terms_id

    def new_tenant_verification(
        self, *, tenant_id: UUID, status: str = "PENDING_VERIFICATION"
    ) -> UUID:
        """Admin tenant-review tests need a tenant_verifications row —
        AdminTenantService requires one to exist (it's the real onboarding
        review record; new_tenant() alone doesn't create it, matching how
        a tenant seeded directly for non-onboarding tests has none)."""
        assert self._conn is not None
        verification_id = uuid4()
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.tenant_verifications (id, tenant_id, status, submitted_at) "
                "VALUES (%s, %s, %s, now())",
                (verification_id, tenant_id, status),
            )
        return verification_id

    def new_tenant_feature_flags(self, *, tenant_id: UUID) -> UUID:
        assert self._conn is not None
        flags_id = uuid4()
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.tenant_feature_flags (id, tenant_id) VALUES (%s, %s)",
                (flags_id, tenant_id),
            )
        return flags_id

    def new_settlement_config(
        self, *, tenant_id: UUID, mode: str = "platform_managed_wallet"
    ) -> UUID:
        """Every test that requests a real withdrawal through PayoutService
        must set this up first — request_withdrawal refuses to run for a
        tenant still in the default direct_merchant_settlement mode.
        Cascade-deleted with the tenant at teardown; no separate cleanup."""
        assert self._conn is not None
        config_id = uuid4()
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO public.tenant_settlement_config (id, tenant_id, mode, is_active) "
                "VALUES (%s, %s, %s, true)",
                (config_id, tenant_id, mode),
            )
        return config_id

    def __exit__(self, *exc_info: object) -> None:
        assert self._conn is not None
        for user_id in self._user_ids:
            delete_user(self._conn, user_id)
        if self.tenant_id is not None:
            delete_tenant(self._conn, self.tenant_id)
        self._conn.close()
