"""Syncs a customer's RADIUS credentials the moment their subscription
activates — the point at which their next hotspot login attempt must be
accepted by FreeRADIUS. Talks directly to the RADIUS Postgres instance
(RADIUS_DATABASE_URL) via raw SQL against the stock schema (see
infrastructure/freeradius/schema/0001_radius_schema.sql) — there are no
declarative ORM models for radcheck/radusergroup, since FreeRADIUS itself
owns that schema, not this app.

A dedicated engine (own NullPool, same reasoning as app/db/session.py:
asyncpg connections are bound to the event loop that created them, so a
pooled connection can outlive and be reused across a different loop under
pytest/Windows — NullPool avoids that by handing out a fresh connection
per checkout) — separate from the primary database's engine.
"""

import hashlib
import hmac
from functools import lru_cache
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


class RadiusNotConfiguredError(RuntimeError):
    """Raised when RADIUS_DATABASE_URL is not set."""


def derive_radius_password(subscription_id: UUID) -> str:
    """A customer's RADIUS password, deterministically derived from their
    subscription id + the server's secrets key — never stored anywhere
    (no new encrypted column needed): whoever needs it (radcheck
    provisioning, or the captive portal handing it to the customer once
    their payment completes) just recomputes it. Without
    SECRETS_ENCRYPTION_KEY, this value is unguessable from the subscription
    id alone.
    """
    key = get_settings().secrets_encryption_key.encode("utf-8")
    message = f"radius-password:{subscription_id}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()[:20]


@lru_cache
def _radius_sessionmaker() -> async_sessionmaker[AsyncSession]:
    settings = get_settings()
    if not settings.radius_database_url:
        raise RadiusNotConfiguredError("RADIUS_DATABASE_URL is not set")
    engine = create_async_engine(str(settings.radius_database_url), poolclass=NullPool, echo=False)
    return async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


def radius_group_name(package_id: UUID) -> str:
    """The radgroupcheck/radgroupreply group a package maps to — see
    infrastructure/freeradius/schema/mikrotik_attributes.md."""
    return f"pkg_{package_id}"


async def sync_package_radius_group(
    *,
    package_id: UUID,
    download_speed_kbps: int | None,
    upload_speed_kbps: int | None,
    session_timeout_seconds: int | None,
    simultaneous_sessions: int,
) -> None:
    """Upserts the radgroupreply/radgroupcheck rows for this package's
    RADIUS group — see infrastructure/freeradius/schema/mikrotik_attributes.md
    for the mapping. Idempotent: safe to call every time a customer is
    provisioned against this package, not just once at package creation."""
    group_name = radius_group_name(package_id)
    session_factory = _radius_sessionmaker()
    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM radgroupreply WHERE groupname = :groupname"),
            {"groupname": group_name},
        )
        await session.execute(
            text("DELETE FROM radgroupcheck WHERE groupname = :groupname"),
            {"groupname": group_name},
        )

        reply_attributes: list[tuple[str, str]] = []
        if download_speed_kbps and upload_speed_kbps:
            reply_attributes.append(
                ("Mikrotik-Rate-Limit", f"{download_speed_kbps}k/{upload_speed_kbps}k")
            )
        if session_timeout_seconds:
            reply_attributes.append(("Session-Timeout", str(session_timeout_seconds)))

        for attribute, value in reply_attributes:
            await session.execute(
                text(
                    "INSERT INTO radgroupreply (groupname, attribute, op, value) "
                    "VALUES (:groupname, :attribute, ':=', :value)"
                ),
                {"groupname": group_name, "attribute": attribute, "value": value},
            )

        await session.execute(
            text(
                "INSERT INTO radgroupcheck (groupname, attribute, op, value) "
                "VALUES (:groupname, 'Simultaneous-Use', ':=', :value)"
            ),
            {"groupname": group_name, "value": str(simultaneous_sessions)},
        )
        await session.commit()


async def provision_customer_radius_access(
    *, customer_phone: str, package_id: UUID, radius_password: str
) -> None:
    """Upserts radcheck (Cleartext-Password) + radusergroup so this
    customer's next PAP auth attempt against FreeRADIUS succeeds and picks
    up the package's group (Mikrotik-Rate-Limit/Session-Timeout/
    Simultaneous-Use radgroupreply/radgroupcheck attributes)."""
    session_factory = _radius_sessionmaker()
    async with session_factory() as session:
        await session.execute(
            text(
                "DELETE FROM radcheck WHERE username = :username "
                "AND attribute = 'Cleartext-Password'"
            ),
            {"username": customer_phone},
        )
        await session.execute(
            text(
                "INSERT INTO radcheck (username, attribute, op, value) "
                "VALUES (:username, 'Cleartext-Password', ':=', :password)"
            ),
            {"username": customer_phone, "password": radius_password},
        )
        await session.execute(
            text("DELETE FROM radusergroup WHERE username = :username"),
            {"username": customer_phone},
        )
        await session.execute(
            text(
                "INSERT INTO radusergroup (username, groupname, priority) "
                "VALUES (:username, :groupname, 1)"
            ),
            {"username": customer_phone, "groupname": radius_group_name(package_id)},
        )
        await session.commit()


async def revoke_customer_radius_access(*, customer_phone: str) -> None:
    """Removes a customer's RADIUS credentials (subscription
    expired/cancelled) so a stale phone/password pair can't keep
    authenticating after their access should have ended."""
    session_factory = _radius_sessionmaker()
    async with session_factory() as session:
        await session.execute(
            text("DELETE FROM radcheck WHERE username = :username"), {"username": customer_phone}
        )
        await session.execute(
            text("DELETE FROM radusergroup WHERE username = :username"),
            {"username": customer_phone},
        )
        await session.commit()
