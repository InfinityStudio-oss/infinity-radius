import asyncio
import sys
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all model modules here so Base.metadata is fully populated before
# autogenerate compares it against the live schema.
import app.models  # noqa: F401,E402
from alembic import context
from app.core.config import get_settings
from app.core.migration_safety import MigrationBlockedError, guard_migration
from app.db.base import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()

# Every Alembic invocation — bare CLI, scripts/migrate.py, a Railway
# migration step — imports this module, so this is the one unavoidable
# place to enforce this. Runs before set_main_option and before anything
# ever opens a connection. See app/core/migration_safety.py for why this
# exists and app/core/config.py for ALLOW_PRODUCTION_MIGRATIONS.
try:
    _migration_target = guard_migration(
        database_url=str(settings.database_url),
        explicit_target=settings.database_migration_target,
        allow_production_migrations=settings.allow_production_migrations,
    )
except MigrationBlockedError as exc:
    print(f"\n[migration-safety] {exc}\n", file=sys.stderr)
    sys.exit(1)

print(f"[migration-safety] migration target classified as: {_migration_target}", file=sys.stderr)

config.set_main_option("sqlalchemy.url", str(settings.database_url))


def run_migrations_offline() -> None:
    context.configure(
        url=str(settings.database_url),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
