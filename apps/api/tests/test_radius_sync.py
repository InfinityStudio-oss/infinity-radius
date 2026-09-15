"""Exercises app/services/radius_sync.py against a REAL RADIUS Postgres
(RADIUS_DATABASE_URL) running the actual FreeRADIUS schema
(infrastructure/freeradius/schema/0001_radius_schema.sql) — verified with a
separate, plain psycopg connection so a bug in radius_sync's own queries
can't mask itself by reading back through the same code path it's meant
to test.
"""

from urllib.parse import urlparse
from uuid import uuid4

import psycopg
import pytest

from app.core.config import get_settings
from app.services.radius_sync import (
    derive_radius_password,
    provision_customer_radius_access,
    revoke_customer_radius_access,
    sync_package_radius_group,
)


def _radius_dsn() -> str:
    url = str(get_settings().radius_database_url)
    parsed = urlparse(url.replace("postgresql+asyncpg://", "postgresql://", 1))
    return (
        f"host={parsed.hostname} port={parsed.port or 5432} "
        f"dbname={parsed.path.lstrip('/')} user={parsed.username} "
        f"password={parsed.password}"
    )


@pytest.fixture
def radius_conn():  # type: ignore[no-untyped-def]
    conn = psycopg.connect(_radius_dsn())
    conn.autocommit = True
    yield conn
    conn.close()


def _cleanup(conn: psycopg.Connection, *, username: str, groupname: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM radcheck WHERE username = %s", (username,))
        cur.execute("DELETE FROM radusergroup WHERE username = %s", (username,))
        cur.execute("DELETE FROM radgroupreply WHERE groupname = %s", (groupname,))
        cur.execute("DELETE FROM radgroupcheck WHERE groupname = %s", (groupname,))


async def test_provision_creates_radcheck_and_radusergroup(radius_conn: psycopg.Connection) -> None:
    username = f"2557{uuid4().hex[:8]}"
    package_id = uuid4()
    try:
        await provision_customer_radius_access(
            customer_phone=username, package_id=package_id, radius_password="test-password-123"
        )

        with radius_conn.cursor() as cur:
            cur.execute(
                "SELECT value FROM radcheck WHERE username = %s "
                "AND attribute = 'Cleartext-Password'",
                (username,),
            )
            password_row = cur.fetchone()
            assert password_row is not None
            (password,) = password_row
            cur.execute(
                "SELECT groupname FROM radusergroup WHERE username = %s", (username,)
            )
            groupname_row = cur.fetchone()
            assert groupname_row is not None
            (groupname,) = groupname_row

        assert password == "test-password-123"
        assert groupname == f"pkg_{package_id}"
    finally:
        _cleanup(radius_conn, username=username, groupname=f"pkg_{package_id}")


async def test_provision_is_idempotent_and_replaces_the_password(
    radius_conn: psycopg.Connection,
) -> None:
    username = f"2557{uuid4().hex[:8]}"
    package_id = uuid4()
    try:
        await provision_customer_radius_access(
            customer_phone=username, package_id=package_id, radius_password="first-password"
        )
        await provision_customer_radius_access(
            customer_phone=username, package_id=package_id, radius_password="second-password"
        )

        with radius_conn.cursor() as cur:
            cur.execute(
                "SELECT value FROM radcheck WHERE username = %s "
                "AND attribute = 'Cleartext-Password'",
                (username,),
            )
            rows = cur.fetchall()

        assert len(rows) == 1  # no duplicate rows from calling it twice
        assert rows[0][0] == "second-password"
    finally:
        _cleanup(radius_conn, username=username, groupname=f"pkg_{package_id}")


async def test_sync_package_radius_group_writes_reply_and_check_attributes(
    radius_conn: psycopg.Connection,
) -> None:
    package_id = uuid4()
    groupname = f"pkg_{package_id}"
    try:
        await sync_package_radius_group(
            package_id=package_id,
            download_speed_kbps=2048,
            upload_speed_kbps=1024,
            session_timeout_seconds=86400,
            simultaneous_sessions=2,
        )

        with radius_conn.cursor() as cur:
            cur.execute(
                "SELECT attribute, value FROM radgroupreply WHERE groupname = %s "
                "ORDER BY attribute",
                (groupname,),
            )
            reply_rows: dict[str, str] = dict(cur.fetchall())
            cur.execute(
                "SELECT attribute, value FROM radgroupcheck WHERE groupname = %s", (groupname,)
            )
            check_rows: dict[str, str] = dict(cur.fetchall())

        assert reply_rows["Mikrotik-Rate-Limit"] == "2048k/1024k"
        assert reply_rows["Session-Timeout"] == "86400"
        assert check_rows["Simultaneous-Use"] == "2"
    finally:
        _cleanup(radius_conn, username="", groupname=groupname)


async def test_revoke_removes_radcheck_and_radusergroup(radius_conn: psycopg.Connection) -> None:
    username = f"2557{uuid4().hex[:8]}"
    package_id = uuid4()
    try:
        await provision_customer_radius_access(
            customer_phone=username, package_id=package_id, radius_password="soon-revoked"
        )
        await revoke_customer_radius_access(customer_phone=username)

        with radius_conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM radcheck WHERE username = %s", (username,))
            radcheck_row = cur.fetchone()
            assert radcheck_row is not None
            (radcheck_count,) = radcheck_row
            cur.execute("SELECT COUNT(*) FROM radusergroup WHERE username = %s", (username,))
            radusergroup_row = cur.fetchone()
            assert radusergroup_row is not None
            (radusergroup_count,) = radusergroup_row

        assert radcheck_count == 0
        assert radusergroup_count == 0
    finally:
        _cleanup(radius_conn, username=username, groupname=f"pkg_{package_id}")


def test_derive_radius_password_is_deterministic() -> None:
    subscription_id = uuid4()
    assert derive_radius_password(subscription_id) == derive_radius_password(subscription_id)


def test_derive_radius_password_differs_per_subscription() -> None:
    assert derive_radius_password(uuid4()) != derive_radius_password(uuid4())
