"""Migration safety guard (app/core/migration_safety.py) — the fix for two
real incidents where a bare `alembic upgrade head` resolved a developer's
local .env's DATABASE_URL to the real production Supabase database, even
though that same .env's ENVIRONMENT was "development". These tests never
touch a real database — classify_database_target/guard_migration are pure
functions over a connection string, never opening a connection.
"""

import pytest

from app.core.migration_safety import (
    MigrationBlockedError,
    classify_database_target,
    guard_migration,
)

_LOCAL_URL = "postgresql+asyncpg://postgres:postgres@localhost:5432/infinity_radius"
_PRODUCTION_URL = (
    "postgresql+asyncpg://postgres.xxxx:secret@aws-1-eu-west-1.pooler.supabase.com:5432/postgres"
)


def test_localhost_classifies_as_local() -> None:
    assert classify_database_target(database_url=_LOCAL_URL) == "local"


def test_loopback_ip_classifies_as_local() -> None:
    url = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/infinity_radius"
    assert classify_database_target(database_url=url) == "local"


def test_real_supabase_host_classifies_as_production() -> None:
    """The exact real-world case that caused both incidents: a genuine
    Supabase pooler hostname, unrecognized by any local-safe pattern."""
    assert classify_database_target(database_url=_PRODUCTION_URL) == "production"


def test_unrecognized_remote_host_defaults_to_production_never_local() -> None:
    """Fail-closed: an ambiguous/unknown host is never assumed safe."""
    url = "postgresql+asyncpg://user:pw@some-new-db-host.example.com:5432/app"
    assert classify_database_target(database_url=url) == "production"


def test_explicit_target_overrides_hostname_heuristic() -> None:
    assert (
        classify_database_target(database_url=_PRODUCTION_URL, explicit_target="staging")
        == "staging"
    )
    assert (
        classify_database_target(database_url=_LOCAL_URL, explicit_target="production")
        == "production"
    )


# ------------------------------------------------------------- guard_migration


def test_local_database_allowed_without_any_authorization() -> None:
    target = guard_migration(
        database_url=_LOCAL_URL, explicit_target=None, allow_production_migrations=False
    )
    assert target == "local"


def test_explicit_test_target_allowed_without_authorization() -> None:
    target = guard_migration(
        database_url=_PRODUCTION_URL, explicit_target="test", allow_production_migrations=False
    )
    assert target == "test"


def test_production_database_blocked_without_authorization() -> None:
    with pytest.raises(MigrationBlockedError) as exc_info:
        guard_migration(
            database_url=_PRODUCTION_URL, explicit_target=None, allow_production_migrations=False
        )
    message = str(exc_info.value)
    assert "blocked" in message.lower()
    assert "explicit operator authorization" in message.lower()
    # Never leaks the connection string/credential.
    assert "secret" not in message
    assert _PRODUCTION_URL not in message


def test_production_database_allowed_with_explicit_authorization() -> None:
    target = guard_migration(
        database_url=_PRODUCTION_URL, explicit_target=None, allow_production_migrations=True
    )
    assert target == "production"


def test_staging_database_blocked_without_authorization() -> None:
    with pytest.raises(MigrationBlockedError):
        guard_migration(
            database_url=_PRODUCTION_URL,
            explicit_target="staging",
            allow_production_migrations=False,
        )


def test_staging_database_allowed_with_explicit_authorization() -> None:
    target = guard_migration(
        database_url=_PRODUCTION_URL, explicit_target="staging", allow_production_migrations=True
    )
    assert target == "staging"


def test_authorization_flag_is_ignored_for_already_safe_targets() -> None:
    """allow_production_migrations=True must never be *required* for a
    genuinely local/test target — it only ever loosens the production/
    staging case, never tightens the local/test case."""
    target = guard_migration(
        database_url=_LOCAL_URL, explicit_target=None, allow_production_migrations=True
    )
    assert target == "local"
