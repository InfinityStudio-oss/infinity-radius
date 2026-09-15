"""Async SQLAlchemy engine/session for the primary (Supabase) Postgres database.

DATABASE_URL is expected in the form `postgresql+asyncpg://user:pass@host:port/db`.

Uses NullPool (a fresh physical connection per checkout, closed on return)
rather than SQLAlchemy's default in-process pool. Two reasons: Supabase
already fronts Postgres with its own pooler (Supavisor/PgBouncer), so a
second pooling layer in the app just adds a class of stale-connection bugs
for no benefit; and asyncpg connections are bound to the event loop that
created them, so any in-process pool that outlives a single loop (as
happens under pytest when each test/`asyncio.run` gets its own loop) can
hand a later request a connection tied to an already-closed loop.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    str(settings.database_url),
    poolclass=NullPool,
    echo=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with AsyncSessionLocal() as session:
        yield session
