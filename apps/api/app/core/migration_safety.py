"""Guards against ever running a real schema migration against the
production Supabase database without deliberate, explicit operator
authorization.

Root cause of the two prior incidents this guards against: a bare
`alembic upgrade head`, run from a developer machine, resolves whatever
DATABASE_URL is configured — which was the real production Supabase
connection string, even though that same .env's ENVIRONMENT was set to
"development". That proves ENVIRONMENT alone is not a trustworthy signal
for "is this safe to migrate" — a developer's local process environment
can claim "development" while pointed at a genuinely production database.
DATABASE_URL's own hostname does not lie the same way: "localhost" always
means local, and anything else is treated as sensitive by default.

Enforced from alembic/env.py — the one path every Alembic invocation
(bare CLI, a wrapper script, Railway's own migration step) goes through,
so there is no way to bypass this by skipping a wrapper. See
docs/architecture.md#migration-safety for the operator runbook.
"""

from urllib.parse import urlparse

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "0.0.0.0"})

# Classifications that never require ALLOW_PRODUCTION_MIGRATIONS.
_SAFE_TARGETS = frozenset({"local", "test"})


class MigrationBlockedError(Exception):
    """Raised to abort a migration before Alembic ever opens a connection.
    The message is always safe to print/log — it names the classification,
    never the connection string, host, database name, or any credential."""


def classify_database_target(*, database_url: str, explicit_target: str | None = None) -> str:
    """Returns "local", "test", "staging", or "production".

    `explicit_target` (Settings.database_migration_target) always wins —
    it exists only for the rare case this hostname heuristic gets a
    genuinely-safe non-localhost target wrong. Absent that, an
    unrecognized or ambiguous host always classifies as "production": the
    maximally cautious answer, never "local"."""
    if explicit_target:
        return explicit_target
    host = urlparse(database_url).hostname
    if host in _LOCAL_HOSTS:
        return "local"
    return "production"


def guard_migration(
    *, database_url: str, explicit_target: str | None, allow_production_migrations: bool
) -> str:
    """Call before any migration touches the database. Returns the
    resolved classification on success; raises MigrationBlockedError
    (never caught here — the caller must let the process exit non-zero)
    otherwise."""
    target = classify_database_target(database_url=database_url, explicit_target=explicit_target)
    if target not in _SAFE_TARGETS and not allow_production_migrations:
        raise MigrationBlockedError(
            f"Production database migration blocked (target classified as {target!r}). "
            "Explicit operator authorization is required. Set "
            "ALLOW_PRODUCTION_MIGRATIONS=true for this one migration command only, then "
            "unset it immediately afterward — see docs/architecture.md#migration-safety."
        )
    return target
