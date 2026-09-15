"""Test environment bootstrap.

Sets required settings via env vars *before* any `app.*` module is imported,
since `app.core.config.get_settings()` is evaluated at import time in
several modules (db session, celery app).

DATABASE_URL is deliberately pinned to local Postgres here via
`os.environ.setdefault` — this wins over whatever DATABASE_URL a real
`.env` file has configured (pydantic-settings checks the process
environment before falling back to `.env`), so the test suite can never
run against a real Supabase project's database no matter what's in a
developer's local `.env`. This is intentional: tests create and delete
real rows (see tests/db_fixtures.py), which must never touch production
data.

Unlike the foundation phase, this suite is now a real integration suite for
everything touching tenant/RBAC resolution (see test_tenant.py,
test_super_admin.py): `get_current_user` looks up tenant_id/roles from
`public.profiles`/`public.profile_roles`, so those tests need an actual
Postgres with the migrations applied — see
tests/fixtures/supabase_auth_stub.sql for the one-time local bootstrap and
`alembic upgrade head` to apply the schema. test_health.py and test_public.py
don't need real connectivity (they mock or exercise "not_configured" paths).
"""

import os
from types import SimpleNamespace
from typing import Any

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres_local_dev@localhost:5432/infinity_radius",
)
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
# Never actually fetched — every test's JWKS resolution is stubbed by the
# autouse `_stub_jwks` fixture below, so this only needs to satisfy
# Settings' required-field validation at import time.
os.environ.setdefault(
    "SUPABASE_JWKS_URL", "https://test.supabase.co/auth/v1/.well-known/jwks.json"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
# Disbursement defaults OFF in real deployments (see app/core/config.py) —
# the test suite turns it on so the maker-checker/Selcom-submission code
# paths it gates can actually be exercised. test_selcom_stubs.py separately
# asserts the real, safe-by-default value via Settings' own field default,
# not this override.
os.environ.setdefault("SELCOM_DISBURSEMENT_ENABLED", "true")

# Registers tests/onboarding_helpers.py's fixtures (mock_supabase_admin) for
# every test module, so onboarding/admin-tenant tests can use it as a plain
# parameter without importing it directly (which ruff flags as a false-
# positive F811 "redefinition" against the same-named test parameter).
pytest_plugins = ["tests.onboarding_helpers"]


@pytest.fixture(autouse=True)
def _stub_jwks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Makes every test's JWT verification resolve its signing key from
    tests/auth_helpers.py's local keypair instead of a real network call
    to SUPABASE_JWKS_URL — the actual jwt.decode() call in
    app.core.security still runs for real (signature/issuer/audience/
    expiry all genuinely checked), only the key *source* is faked. See
    tests/test_jwks_auth.py for tests that exercise this directly.
    """
    import app.core.security as security_module
    from tests.auth_helpers import TEST_PUBLIC_KEY

    class _FakeJWKClient:
        def get_signing_key_from_jwt(self, token: str) -> Any:
            return SimpleNamespace(key=TEST_PUBLIC_KEY)

    monkeypatch.setattr(security_module, "_get_jwk_client", lambda: _FakeJWKClient())
