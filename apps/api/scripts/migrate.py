"""Thin, friendlier front door onto Alembic — the real safety guard lives
in alembic/env.py (app/core/migration_safety.py) and fires the same way
whether you use this script or call `alembic` directly; this file never
duplicates that logic, it only prints clearer guidance around it.

Usage:
    python -m scripts.migrate current
    python -m scripts.migrate upgrade head
    python -m scripts.migrate downgrade -1

For a production migration, set ALLOW_PRODUCTION_MIGRATIONS=true for this
one invocation only (Railway: set it, run this one migration job, then
unset it again) — see docs/architecture.md#migration-safety.
"""

import sys

from alembic.config import main as alembic_main

from app.core.config import get_settings
from app.core.migration_safety import classify_database_target


def main() -> None:
    settings = get_settings()
    target = classify_database_target(
        database_url=str(settings.database_url),
        explicit_target=settings.database_migration_target,
    )
    print(f"[migrate] target classified as: {target}", file=sys.stderr)
    if target not in ("local", "test") and not settings.allow_production_migrations:
        print(
            "[migrate] this target requires ALLOW_PRODUCTION_MIGRATIONS=true — "
            "set it for this one command only, then unset it. See "
            "docs/architecture.md#migration-safety.",
            file=sys.stderr,
        )
        # Not exiting here — alembic/env.py enforces this for real on the
        # next line; this message just explains the failure that's about
        # to happen instead of a bare stack trace.

    alembic_main(argv=sys.argv[1:])


if __name__ == "__main__":
    main()
